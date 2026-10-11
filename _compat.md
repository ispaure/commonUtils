# Package layout

Implementation remains grouped into filesystem, formats, archives, runtime,
integrations, configuration, persistence and ui. Launchers and tests remain at the
root. Use [architecture](docs/developer/architecture.md) for responsibility boundaries.

Cross-cutting developer documentation lives in `docs/developer/`; specialized API
references stay beside implementation, and shared user workflows in component-local
`user_docs/`. Documentation organization must not change import/package structure.

## Compatibility and reconciliation

See [compatibility](docs/developer/compatibility.md) for aliases, consumer namespaces,
persisted formats and upgrade validation. `_compat.py` remains the single lazy
historical import adapter. New code uses canonical imports.

## Validation

See [maintenance](docs/developer/maintenance.md) and [test commands](tests/README.md).

## Filesystem and operation contracts

See [public APIs](docs/developer/public-apis.md) for file operations and traversal,
[architecture](docs/developer/architecture.md#persistence-and-failure-boundaries)
for cancellation/transaction boundaries, and the owning package references for
archive, download and process details. Link traversal policy is operation-specific.

## Package layout and compatibility

This retained entry point replaces the earlier combined layout/migration guide.
The [developer hub](docs/developer/README.md) is the primary navigation for integrators
and maintainers; the former layout checkpoint is `commonUtils-Pre-Refactor`.
