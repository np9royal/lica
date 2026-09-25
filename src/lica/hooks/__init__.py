from lica.hooks.base import HookAdapter, HookEvent
from lica.hooks.claude_code import ClaudeCodeAdapter
from lica.hooks.generic import GenericAdapter

ADAPTERS: dict[str, type[HookAdapter]] = {
    "claude-code": ClaudeCodeAdapter,
    "generic": GenericAdapter,
}


def get_adapter(name: str) -> HookAdapter:
    if name not in ADAPTERS:
        raise ValueError(f"unknown adapter {name!r}; available: {sorted(ADAPTERS)}")
    return ADAPTERS[name]()


__all__ = ["HookAdapter", "HookEvent", "get_adapter", "ADAPTERS"]
