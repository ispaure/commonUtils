# External applications

Import from `commonUtils.integrations.applications`. Implementation and public exports live in
[`__init__.py`](../../../../../integrations/applications/__init__.py).

Public entry points: `App`, `DiskApp`, `StoreApp`, `Flatpak`, `ensure_executable`, `AppImage`, `validate_exec`, `set_app_executable_permissions`, `open_uri`

[Library overview](../../../overview.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `set_app_executable_permissions` | For macOS, gets the run permissions for a given .app by entering chmod +x in the terminal. |
| `open_uri` | Open a URI using the operating system's registered protocol handler. |

Application and URI launch adapters remain desktop-only. On iOS/Android they
raise `runtime.platform.capabilities.UnsupportedCapabilityError` before executing
an external application. The host must provide a verified mobile adapter in a
future integration; no desktop executable is selected as a fallback.
