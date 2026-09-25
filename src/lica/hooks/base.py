"""Hook adapter contract: agent-native payload <-> lica event <-> native output."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from lica.packs.schema import HookPoint


@dataclass
class HookEvent:
    hook_point: HookPoint
    tool_name: str | None = None
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_output: Any = None
    context: dict[str, Any] = field(default_factory=dict)

    def template_context(self) -> dict[str, Any]:
        return {
            "hook": self.hook_point.value,
            "tool_name": self.tool_name or "",
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
            **self.context,
        }


class HookAdapter(ABC):
    """Translates one agent's hook protocol to/from lica."""

    name: str = "base"

    @abstractmethod
    def parse(self, payload: dict[str, Any]) -> HookEvent:
        """Native hook payload -> normalized event."""

    @abstractmethod
    def emit(
        self, event: HookEvent, action: str, reason: str, pack_results: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """(event, verdict) -> JSON to print on stdout, or None for no output."""
