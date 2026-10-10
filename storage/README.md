# storage

Platform-standard commonUtils caches and private disposable workspaces.

Import from `commonUtils.storage`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `cache_directory`, `temporary_directory`, `temporary_workspace`

[Library overview](../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `temporary_workspace` | Return a private TemporaryDirectory context under the shared Temp area. |
