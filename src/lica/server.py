"""Localhost decision daemon — keeps the Laya router warm between hook calls."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from lica.config import Config
from lica.engine import DecisionEngine
from lica.hooks.base import HookEvent
from lica.log import DecisionLog
from lica.packs.schema import HookPoint, Pack


class DecideRequest(BaseModel):
    hook: str = "post_tool_call"
    tool_name: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)
    tool_output: Any = None
    context: dict[str, Any] = Field(default_factory=dict)


def create_app(
    config: Config,
    packs: list[Pack],
    engine: DecisionEngine | None = None,
    project_dir: Path | None = None,
) -> FastAPI:
    engine = engine or DecisionEngine(config)
    log = DecisionLog((project_dir or Path.cwd()) / config.lica.log_path)
    state: dict[str, Any] = {"started": time.time(), "decisions": 0, "warmed": False}

    app = FastAPI(title="lica", docs_url=None, redoc_url=None)
    app.state.daemon_state = state

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "warmed": state["warmed"],
            "packs": len(packs),
            "uptime_s": round(time.time() - state["started"], 1),
        }

    @app.post("/decide")
    def decide(req: DecideRequest) -> dict[str, Any]:
        try:
            hook_point = HookPoint.parse(req.hook)
        except ValueError:
            return {
                "action": config.lica.on_error,
                "reason": f"unknown hook point {req.hook!r}",
                "packs": [],
            }

        event = HookEvent(
            hook_point=hook_point,
            tool_name=req.tool_name,
            tool_input=req.tool_input,
            tool_output=req.tool_output,
            context=req.context,
        )
        merged, verdicts, errors = engine.evaluate_event(
            packs, hook_point, event.template_context()
        )
        state["decisions"] += 1
        state["warmed"] = True

        shadow = config.lica.mode == "shadow"
        pack_results = [
            {
                "name": v.pack,
                "action": v.action.value,
                "reason": v.reason,
                "latency_ms": round(v.latency_ms, 1),
                "answers": v.answers,
            }
            for v in verdicts
        ]

        action = merged.action.value if merged else "allow"
        reason = merged.reason if merged else ""

        log.record(
            {
                "hook": hook_point.value,
                "tool": req.tool_name,
                "action": action,
                "enforced": (not shadow) and action in ("block", "ask"),
                "shadow": shadow,
                "reason": reason,
                "packs": [{"name": v.pack, "action": v.action.value} for v in verdicts],
                "errors": errors,
            }
        )

        return {
            "action": "allow" if shadow else action,
            "would_action": action if shadow else None,
            "reason": reason,
            "packs": pack_results,
            "errors": errors,
        }

    @app.post("/warmup")
    def warmup() -> dict[str, Any]:
        engine.warmup()
        state["warmed"] = True
        return {"status": "warmed"}

    return app


def _mark_warmed(app: FastAPI) -> None:
    app.state.daemon_state["warmed"] = True


def run_server(config: Config, packs: list[Pack], project_dir: Path | None = None) -> None:
    import uvicorn

    engine = DecisionEngine(config)
    app = create_app(config, packs, engine, project_dir)

    # Warm the router in the background so the server binds fast; the first real
    # hook may still pay model-load cost if it lands before warmup finishes.
    def _warm() -> None:
        try:
            engine.warmup()
            _mark_warmed(app)
        except Exception:
            pass

    threading.Thread(target=_warm, daemon=True).start()
    uvicorn.run(
        app, host=config.lica.server_host, port=config.lica.server_port, log_level="warning"
    )
