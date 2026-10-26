# Integrations

Adapters for external applications and tools. Optional dependencies belong to the
adapter that uses them; importing this area does not start tools or import Qt.

- `applications`: launch and inspect desktop applications.
- `web`: open URLs using the system browser.
- `steam`: Steam application helpers.
- `wrappers`: command execution, PowerShell, Perforce, SQL and metadata adapters.

Example: `from commonUtils.integrations.web import open_url`.

[Command wrappers](wrappers/wrappers.md) · [Library overview](../../overview.md).

## Pages

- [External applications](applications/applications.md)
- [Steam launch detection](steam/steam.md)
- [Open a web link](web/web.md)
