# linkUtils

Shared linkUtils API. The public import path is unchanged after moving its implementation into this package.

Import from `commonUtils.linkUtils`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `is_junction`, `delete_symbolic_link`, `create_symbolic_link`, `update_symbolic_link`

[Library overview](../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `is_junction` | Returns whether a path is a Windows junction. |
| `delete_symbolic_link` | Deletes a symbolic link without deleting the target it points to. |
| `create_symbolic_link` | Creates a symbolic link at destination pointing to source. |
| `update_symbolic_link` | Creates or updates a symbolic link at destination pointing to source. |
