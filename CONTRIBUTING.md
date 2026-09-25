# Contributing to lica

Thanks for your interest! lica is Apache-2.0; by submitting a contribution you
agree to license your work under the same terms (Developer Certificate of Origin —
a `Signed-off-by:` line in your commits is appreciated but not required yet).

## Development setup

```bash
pip install -e ".[dev]"
pytest                # unit tests (Laya router is mocked — no model download)
pytest -m slow        # additionally run the real-model CPU smoke test
ruff check . && ruff format --check .
```

CI config lives at the repo root as `ci.yml` — move it to
`.github/workflows/ci.yml` to enable GitHub Actions (the web UI's "set up a
workflow yourself" flow accepts it directly).

## Writing a decision pack

Packs are YAML and live in `src/lica/packs/builtin/` (bundled) or
`.lica/packs/` / `~/.lica/packs/` (per project/user). A pack needs:

- `pack` — kebab-case name
- `hooks` — hook points: `pre_tool_call`, `post_tool_call`, `user_prompt`,
  `pre_compact`, `notification`, `stop` (Claude Code names like `PostToolUse`
  are accepted)
- `match.tools` — tool names or `prefix*` globs
- `state_template` — Jinja2 over `tool_name`, `tool_input`, `tool_output`,
  `cwd`, `hook`; `truncate` and `tojson` filters available
- `questions` — `choice` / `score` / `noul` (see README table)
- `decision` — ordered rules: `{if: {question, eq|gte|lte|in}, action, reason}`
  ending in `{default: allow}`

Design guidance for packs:

- Ask sharp questions. A `noul` of 0.5 means "can't tell", not "medium" — write
  conditions that are actually yes/no.
- Prefer `ask` over `block` for ambiguous classes; blocks should be reserved
  for clearly-bad verdicts. Guardrails that cry wolf get uninstalled.
- Pin `model: typed-decisions` unless the pack specifically needs multilingual.
- Test in `mode = "shadow"` first and iterate with `lica report`.

## Commit style

Plain-text commit messages, imperative mood, no tool attribution footers.

## Reporting security issues

If you find a way a pack verdict can be bypassed or a path where lica itself
leaks data, please open a private security advisory rather than a public issue.
