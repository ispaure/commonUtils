# Docking workspaces

Docking, tab gestures, splitting, floating windows and native workspace menus.

Import implementations from `commonUtils.ui.workspaces.<module>`.
The former `commonUtils.ui.<module>` paths remain compatibility aliases to the
same module objects, including their registries and patch targets. Package imports
do not eagerly load their widgets.

## Modules

- `workspace`
- `workspace_drag`
- `workspace_layout`
- `workspace_window`
- `workspace_policy`
- `workspace_menus`
- `workspace_cocoa`
- `scoped_tabs`

[Workspace contracts](../workspaces.md), [layout](../workspace_layout.md) and [scoped tabs](../scoped_tabs.md).
