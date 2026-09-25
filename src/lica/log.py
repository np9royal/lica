"""JSONL decision log."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DecisionLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, entry: dict[str, Any]) -> None:
        entry = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass  # logging must never break a hook

    def iter(self) -> Iterator[dict[str, Any]]:
        if not self.path.is_file():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
