# osUtils

Shared osUtils API. The public import path is unchanged after moving its implementation into this package.

Import from `commonUtils.osUtils`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `OS`, `get_os`, `Arch`, `get_arch`, `get_os_path`

[Library overview](../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `get_os_path` | Returns the correct path based on the current operating system. |
