"""Jinja2 rendering for pack state templates and rule reasons."""

from __future__ import annotations

import json
from typing import Any

from jinja2 import ChainableUndefined, Environment

_env: Environment | None = None


def _truncate(value: Any, length: int = 2000, end: str = "...") -> str:
    s = "" if value is None else str(value)
    return s if len(s) <= length else s[: max(0, length - len(end))] + end


def _tojson(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def get_env() -> Environment:
    global _env
    if _env is None:
        env = Environment(undefined=ChainableUndefined, autoescape=False)
        env.filters["truncate"] = _truncate
        env.filters["tojson"] = _tojson
        _env = env
    return _env


def render_state(template_src: str, context: dict[str, Any]) -> str:
    return get_env().from_string(template_src).render(**context)


def render_reason(template_src: str, context: dict[str, Any]) -> str:
    return render_state(template_src, context)
