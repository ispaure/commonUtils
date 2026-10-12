# Docking workspaces

Docking, tab gestures, splitting, floating windows and native workspace menus.

Import implementations from `commonUtils.ui.workspaces.<module>`.
Import widgets and helpers directly from these modules. Package imports do not
eagerly load their widgets. Former flat `commonUtils.ui.<module>` forwarding
modules have been removed; update imports and mock patch targets to this package.

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
