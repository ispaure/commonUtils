# debugUtils

Shared debugUtils API. The public import path is unchanged after moving its implementation into this package.

Import from `commonUtils.debugUtils`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `print_debug_msg`, `noninteractive_logging`, `DebugException`, `Severity`, `DebugLogger`

[Library overview](../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `noninteractive_logging` | Workers log and raise failures; their owner presents errors on the GUI thread. |
