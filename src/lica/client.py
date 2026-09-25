"""Thin client for the lica daemon, used by `lica hook`."""

from __future__ import annotations

from typing import Any

import httpx


class DaemonUnavailable(Exception):
    pass


def decide(
    payload: dict[str, Any],
    host: str = "127.0.0.1",
    port: int = 6133,
    timeout: float = 10.0,
) -> dict[str, Any]:
    try:
        resp = httpx.post(
            f"http://{host}:{port}/decide",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as e:
        raise DaemonUnavailable(str(e)) from e


def health(host: str = "127.0.0.1", port: int = 6133, timeout: float = 2.0) -> dict[str, Any]:
    resp = httpx.get(f"http://{host}:{port}/healthz", timeout=timeout)
    resp.raise_for_status()
    return resp.json()
