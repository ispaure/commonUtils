# Integrations

Adapters for external applications and tools. Optional dependencies belong to the
adapter that uses them; importing this area does not start tools or import Qt.

- `applications`: launch and inspect desktop applications.
- `web`: open URLs using the system browser.
- `steam`: Steam application helpers.
- `wrappers`: command execution, PowerShell, Perforce, SQL and metadata adapters.

Example: `from commonUtils.integrations.web import open_url`.

[Command wrappers](wrappers/README.md) · [Library overview](../README.md).
