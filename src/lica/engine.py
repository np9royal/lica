"""Decision engine: packs -> Laya questions -> typed answers -> verdicts."""

from __future__ import annotations

import threading
import time
from typing import Any

from lica.config import Config
from lica.decision import Verdict, apply_rules, merge_verdicts
from lica.packs.schema import HookPoint, Pack
from lica.state import render_state


class DecisionEngine:
    """Wraps a Laya Router with pack evaluation. Router is injectable for tests."""

    def __init__(self, config: Config | None = None, router: Any = None) -> None:
        self.config = config or Config()
        self._router = router
        self._lock = threading.Lock()

    @property
    def router(self) -> Any:
        if self._router is None:
            with self._lock:
                if self._router is None:
                    from laya import Router

                    self._router = Router()
        return self._router

    def warmup(self) -> None:
        """Force model load + a trivial predict so first hook call is fast."""
        kwargs: dict[str, Any] = {}
        if self.config.lica.model:
            kwargs["model"] = self.config.lica.model
        self.router.predict(
            "warmup",
            {"ok": {"type": "noul", "instructions": "Is this a warmup call?"}},
            **kwargs,
        )

    def matching_packs(
        self, packs: list[Pack], hook_point: HookPoint, tool_name: str
    ) -> list[Pack]:
        out = []
        for pack in packs:
            if not self.config.pack_enabled(pack.pack):
                continue
            if hook_point not in pack.hooks:
                continue
            tools = self.config.pack_tools(pack.pack)
            if tools is not None:
                if not _match_any(tools, tool_name):
                    continue
            elif not pack.match.matches(tool_name):
                continue
            out.append(pack)
        return out

    def evaluate(self, pack: Pack, context: dict[str, Any]) -> Verdict:
        state = render_state(pack.state_template, context)
        kwargs: dict[str, Any] = {}
        model = self.config.pack_model(pack.pack, pack.model)
        if model:
            kwargs["model"] = model
        if pack.max_len:
            kwargs["max_len"] = pack.max_len

        t0 = time.perf_counter()
        result = self.router.predict(state, pack.questions_for_laya(), **kwargs)
        latency_ms = (time.perf_counter() - t0) * 1000

        answers = _normalize_answers(pack, result.get("answers", {}))
        thresholds = self.config.pack_thresholds(pack.pack)

        def render(template: str) -> str:
            return render_state(template, {**context, "answers": answers})

        verdict = apply_rules(pack, answers, render, thresholds)
        verdict.latency_ms = latency_ms
        return verdict

    def evaluate_event(
        self,
        packs: list[Pack],
        hook_point: HookPoint,
        context: dict[str, Any],
    ) -> tuple[Verdict | None, list[Verdict], list[str]]:
        """Run all matching packs over an event. Returns (merged, all, errors)."""
        tool_name = str(context.get("tool_name") or "")
        applicable = self.matching_packs(packs, hook_point, tool_name)
        verdicts: list[Verdict] = []
        errors: list[str] = []
        for pack in applicable:
            try:
                verdicts.append(self.evaluate(pack, context))
            except Exception as e:  # a broken pack must not break the hook
                errors.append(f"{pack.pack}: {e}")
        return merge_verdicts(verdicts), verdicts, errors


def _match_any(patterns: list[str], tool_name: str) -> bool:
    for pat in patterns:
        if pat == "*":
            return True
        if pat.endswith("*"):
            if tool_name.startswith(pat[:-1]):
                return True
        elif tool_name == pat:
            return True
    return False


def _normalize_answers(pack: Pack, raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Attach the question type to each answer so rule eval knows the scalar."""
    out: dict[str, dict[str, Any]] = {}
    for name, question in pack.questions.items():
        answer = dict(raw.get(name) or {})
        answer["type"] = question.type
        out[name] = answer
    return out
