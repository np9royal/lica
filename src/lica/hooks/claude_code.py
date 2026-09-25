"""Claude Code hook adapter (PreToolUse / PostToolUse and friends).

Protocol: the agent writes a JSON event to the hook command's stdin and reads a
JSON decision from stdout. PreToolUse decisions go in
hookSpecificOutput.permissionDecision; PostToolUse uses the top-level
`decision`/`reason` pair. `ask` on PostToolUse is emitted as additionalContext
so it advises without hard-blocking the tool result.
"""

from __future__ import annotations

from typing import Any

from lica.hooks.base import HookAdapter, HookEvent
from lica.packs.schema import HookPoint

_EVENT_NAMES = {
    HookPoint.PRE_TOOL_CALL: "PreToolUse",
    HookPoint.POST_TOOL_CALL: "PostToolUse",
    HookPoint.USER_PROMPT: "UserPromptSubmit",
    HookPoint.PRE_COMPACT: "PreCompact",
    HookPoint.NOTIFICATION: "Notification",
    HookPoint.STOP: "Stop",
}


class ClaudeCodeAdapter(HookAdapter):
    name = "claude-code"

    def parse(self, payload: dict[str, Any]) -> HookEvent:
        hook_point = HookPoint.parse(payload.get("hook_event_name") or "PostToolUse")
        context = {
            k: v
            for k, v in payload.items()
            if k not in {"hook_event_name", "tool_name", "tool_input", "tool_response"}
        }
        return HookEvent(
            hook_point=hook_point,
            tool_name=payload.get("tool_name"),
            tool_input=payload.get("tool_input") or {},
            tool_output=payload.get("tool_response"),
            context=context,
        )

    def emit(
        self, event: HookEvent, action: str, reason: str, pack_results: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        event_name = _EVENT_NAMES.get(event.hook_point, "PostToolUse")

        if event.hook_point == HookPoint.PRE_TOOL_CALL:
            decision = {"block": "deny", "ask": "ask"}.get(action)
            if decision is None:
                return None  # allow / log: clean exit, no output
            out = {
                "hookSpecificOutput": {"hookEventName": event_name, "permissionDecision": decision}
            }
            if reason:
                out["hookSpecificOutput"]["permissionDecisionReason"] = reason
            return out

        if action == "block":
            return {"decision": "block", "reason": reason or "blocked by lica"}
        if action == "ask":
            return {
                "hookSpecificOutput": {
                    "hookEventName": event_name,
                    "additionalContext": f"lica recommends review: {reason or 'flagged by a decision pack'}",
                }
            }
        return None  # allow / log: clean exit, no output

    def settings_snippet(self, command: str, hook_points: list[HookPoint]) -> dict[str, Any]:
        """Claude Code settings.json fragment for the given hook points."""
        hooks: dict[str, Any] = {}
        for point in hook_points:
            event_name = _EVENT_NAMES.get(point)
            if event_name is None:
                continue
            hooks.setdefault(event_name, []).append(
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": command}],
                }
            )
        return {"hooks": hooks}
