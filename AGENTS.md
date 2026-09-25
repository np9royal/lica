# AGENTS.md

## What this is

`lica` — typed decision packs for coding agents, powered by Laya (Apache-2.0
System 1 decision model). Packs are YAML: a Jinja state template + typed
questions (choice/score/noul) + ordered verdict rules (allow/block/ask/log).

## Layout

- `src/lica/packs/schema.py` — pack YAML schema (pydantic)
- `src/lica/packs/loader.py` — pack discovery: builtin → ~/.lica/packs → .lica/packs
- `src/lica/packs/builtin/*.yaml` — bundled packs
- `src/lica/decision.py` — rule evaluation (declarative, no eval)
- `src/lica/engine.py` — Laya Router wrapper; router injectable for tests
- `src/lica/server.py` / `client.py` — localhost daemon + thin hook client
- `src/lica/hooks/` — adapters (claude_code, generic stdin/stdout JSON)
- `src/lica/cli.py` — typer CLI: init / serve / hook / run / packs / report / doctor

## Build & test

```bash
pip install -e ".[dev]"
pytest                 # unit tests; Laya Router is mocked, no model download
pytest -m slow         # real-model CPU smoke test (downloads weights)
ruff check . && ruff format --check .
```

Entry point: `lica` (or `python -m lica`). Daemon: `lica serve` on
127.0.0.1:6133 (`POST /decide`, `GET /healthz`).

## Conventions

- New verdict-affecting logic needs a unit test with a fake router — never
  download weights in unit tests (mark real-model tests `@pytest.mark.slow`).
- Pack YAML names are kebab-case slugs; rule conditions are declarative only.
- Apache-2.0; no AI-attribution trailers in commit messages.
