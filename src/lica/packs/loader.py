"""Pack discovery: built-ins -> ~/.lica/packs -> .lica/packs (later overrides by name)."""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass
from pathlib import Path

from lica.packs.schema import Pack

BUILTIN_PACKAGE = "lica.packs.builtin"
USER_PACK_DIR = Path.home() / ".lica" / "packs"
PROJECT_PACK_DIR = ".lica/packs"


@dataclass
class LoadedPack:
    pack: Pack
    source: str  # "builtin" or the file path it came from


def _load_dir(directory: Path, into: dict[str, LoadedPack]) -> list[str]:
    """Load every *.yaml/*.yml in a directory. Returns per-file error strings."""
    errors: list[str] = []
    if not directory.is_dir():
        return errors
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in (".yaml", ".yml") or not path.is_file():
            continue
        try:
            pack = Pack.from_yaml(path.read_text(encoding="utf-8"), source=str(path))
            into[pack.pack] = LoadedPack(pack, str(path))
        except (OSError, ValueError) as e:
            errors.append(str(e))
    return errors


def load_packs(project_dir: Path | None = None) -> tuple[dict[str, LoadedPack], list[str]]:
    """Load all packs. Returns (name -> LoadedPack, errors)."""
    packs: dict[str, LoadedPack] = {}
    errors: list[str] = []

    for resource in importlib.resources.files(BUILTIN_PACKAGE).iterdir():
        if resource.name.endswith((".yaml", ".yml")):
            try:
                pack = Pack.from_yaml(
                    resource.read_text(encoding="utf-8"), source=f"builtin:{resource.name}"
                )
                packs[pack.pack] = LoadedPack(pack, "builtin")
            except ValueError as e:
                errors.append(str(e))

    errors += _load_dir(USER_PACK_DIR, packs)
    if project_dir is not None:
        errors += _load_dir(project_dir / PROJECT_PACK_DIR, packs)
    return packs, errors
