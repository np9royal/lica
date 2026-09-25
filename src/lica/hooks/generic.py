"""Generic hook adapter — documented stdin/stdout JSON protocol for any agent.

stdin:
    {
      "hook_point": "post_tool_call",     // or any native name (PostToolUse, ...)
      "tool_name": "WebFetch",
      "tool_input": {...},
      "tool_output": "...",              // optional
      "context": {"cwd": "...", ...}     // optional extras
    }

stdout:
    {"action": "allow|block|ask|log", "reason": "...", "packs": [{...}]}
"""

from __future__ import annotations

from typing import Any

from lica.hooks.base import HookAdapter, HookEvent
from lica.packs.schema import HookPoint


class GenericAdapter(HookAdapter):
    name = "generic"

    def parse(self, payload: dict[str, Any]) -> HookEvent:
        hook_point = HookPoint.parse(
            payload.get("hook_point") or payload.get("hook_event_name") or "post_tool_call"
        )
        extra = dict(payload.get("context") or {})
        for k, v in payload.items():
            if k not in {
                "hook_point",
                "hook_event_name",
                "tool_name",
                "tool_input",
                "tool_output",
                "tool_response",
                "context",
            }:
                extra.setdefault(k, v)
        return HookEvent(
            hook_point=hook_point,
            tool_name=payload.get("tool_name"),
            tool_input=payload.get("tool_input") or {},
            tool_output=payload.get("tool_output", payload.get("tool_response")),
            context=extra,
        )

    def emit(
        self, event: HookEvent, action: str, reason: str, pack_results: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        return {"action": action, "reason": reason, "packs": pack_results}
