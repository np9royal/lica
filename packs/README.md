# Community packs

Drop-in decision packs for lica. Copy any `.yaml` here into your project's
`.lica/packs/` (or `~/.lica/packs/` for all projects) — files there override
built-ins by pack name.

Each file must validate against the pack schema (`lica packs` will report
errors). See the built-in packs under `src/lica/packs/builtin/` for reference,
and CONTRIBUTING.md for design guidance.

PRs with new packs are welcome — include a description, a sensible default
policy (`ask` beats `block` for ambiguous classes), and a note on any
thresholds you tuned.
