# steamUtils

Shared steamUtils API. The public import path is unchanged after moving its implementation into this package.

Import from `commonUtils.steamUtils`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `is_linux_steam_big_picture`

[Library overview](../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `is_linux_steam_big_picture` | Return if the application was launched in Linux Steam Big Picture Mode  |
