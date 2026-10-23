# commonUtils contributor guidance

Read [architecture](docs/developer/architecture.md),
[extension contracts](docs/developer/extension-points.md) and
[integration contracts](docs/developer/contracts.md) before changing shared interfaces.

- Keep application workflows, plugin discovery and dependency policy in consumers.
- Use canonical direct module imports and preserve namespace isolation, established public interfaces,
  persisted formats and cooperative UI shutdown. Do not infer stability from names.
- Flat UI forwarding modules have been removed. Use the grouped UI packages for imports
  and patch targets; do not recreate legacy aliases.
- Update the owning API guide for contract changes and `docs/user/` for
  shared interactive behavior. Follow [documentation ownership](docs/developer/maintenance.md).
- Keep README concise; cross-cutting developer guidance lives in `docs/developer/`,
  API references in `docs/reference/`, and user guides in `docs/user/`.
- Every wiki page starts with an H1 title. Every folder has a same-named landing
  linked by its parent; `docs/docs.md` is the shared wiki root. Source-local
  README/user_docs files remain short compatibility links, not duplicate guides.
- Validate with isolated fixtures/caches and relevant shared/consumer tests. Report
  unavailable platform/consumer checks explicitly. See [testing](docs/reference/tests/tests.md).

## Branch workflow

Work on the current development branch by default. Create a separate branch only
when there is a concrete reason, such as isolating concurrent work or a risky
experiment; do not create `codex/*` branches automatically.
