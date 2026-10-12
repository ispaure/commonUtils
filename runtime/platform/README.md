# Operating system and architecture

Import from `commonUtils.runtime.platform`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `OS`, `get_os`, `Arch`, `get_arch`, `get_os_path`

[Library overview](../../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `get_os_path` | Returns the correct path based on the current operating system. |

`OS.IOS` and `OS.ANDROID` are additive enum members. `get_os()` recognizes modern
mobile interpreter identifiers and legacy runtime markers before desktop checks.
Unknown platforms still raise `RuntimeError`. `get_os_path(path_win=None,
path_mac=None, path_linux=None)` keeps its desktop-only signature and raises on
mobile; callers must supply their own sandbox paths. See the
[mobile audit](../../docs/developer/mobile-foundation.md).
