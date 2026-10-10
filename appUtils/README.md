# appUtils

Shared appUtils API. The public import path is unchanged after moving its implementation into this package.

Import from `commonUtils.appUtils`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `App`, `DiskApp`, `StoreApp`, `Flatpak`, `ensure_executable`, `AppImage`, `validate_exec`, `set_app_executable_permissions`, `open_uri`

[Library overview](../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `set_app_executable_permissions` | For macOS, gets the run permissions for a given .app by entering chmod +x in the terminal. |
| `open_uri` | Open a URI using the operating system's registered protocol handler. |
