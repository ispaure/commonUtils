# commonUtils contributor guidance

Read [architecture](docs/developer/architecture.md),
[extension contracts](docs/developer/extension-points.md) and
[integration contracts](docs/developer/contracts.md) before changing shared interfaces.

- Keep application workflows, plugin discovery and dependency policy in consumers.
- Use canonical direct module imports and preserve namespace isolation, established public interfaces,
  persisted formats and cooperative UI shutdown. Do not infer stability from names.
- Flat UI forwarding modules have been removed. Use the grouped UI packages for imports
  and patch targets; do not recreate legacy aliases.
- Update the owning API guide for contract changes and component `user_docs/` for
  shared interactive behavior. Follow [documentation ownership](docs/developer/maintenance.md).
- Keep README concise; cross-cutting developer guidance lives in `docs/developer/`,
  detailed references beside their implementations, and user guides beside components.
- Validate with isolated fixtures/caches and relevant shared/consumer tests. Report
  unavailable platform/consumer checks explicitly. See [testing](tests/README.md).
