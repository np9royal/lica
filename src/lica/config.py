"""lica.toml configuration."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]

CONFIG_FILENAME = "lica.toml"
DEFAULT_PORT = 6133

DEFAULT_CONFIG = """\
[lica]
# Laya checkpoint: "typed-decisions" (recommended), "english", "multilingual"
model = "typed-decisions"
# "enforce" applies verdicts; "shadow" logs what would happen without blocking
mode = "enforce"
# "allow" fails open if the daemon is unreachable; "block" fails closed
on_error = "allow"
server_port = 6133
log_path = ".lica/decisions.jsonl"

[hooks]
claude_code = true

# Per-pack overrides:
# [packs.injection-guard]
# enabled = true
# thresholds.hostile = 0.7
"""


class PackConfig(BaseModel):
    enabled: bool = True
    model: str | None = None
    thresholds: dict[str, float] = Field(default_factory=dict)
    tools: list[str] | None = None  # override the pack's tool matcher


class LicaSettings(BaseModel):
    model: str | None = "typed-decisions"
    mode: Literal["enforce", "shadow"] = "enforce"
    on_error: Literal["allow", "block"] = "allow"
    server_host: str = "127.0.0.1"
    server_port: int = DEFAULT_PORT
    log_path: str = ".lica/decisions.jsonl"


class Config(BaseModel):
    lica: LicaSettings = Field(default_factory=LicaSettings)
    packs: dict[str, PackConfig] = Field(default_factory=dict)
    hooks: dict[str, bool] = Field(default_factory=dict)

    def pack_enabled(self, name: str) -> bool:
        cfg = self.packs.get(name)
        return cfg.enabled if cfg else True

    def pack_thresholds(self, name: str) -> dict[str, float]:
        cfg = self.packs.get(name)
        return cfg.thresholds if cfg else {}

    def pack_model(self, name: str, pack_default: str | None) -> str | None:
        cfg = self.packs.get(name)
        if cfg and cfg.model:
            return cfg.model
        return pack_default or self.lica.model

    def pack_tools(self, name: str) -> list[str] | None:
        cfg = self.packs.get(name)
        return cfg.tools if cfg else None


def find_config(start: Path | None = None) -> Path | None:
    """Walk upward from `start` (or cwd) looking for lica.toml."""
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_config(path: Path | None = None) -> Config:
    """Load lica.toml from `path`, or search upward from cwd. Empty config if none."""
    if tomllib is None:
        raise RuntimeError("tomllib/tomli unavailable; install tomli on Python < 3.11")
    found = path or find_config()
    if found is None:
        return Config()
    data = tomllib.loads(found.read_text(encoding="utf-8"))
    return Config.model_validate(data)
