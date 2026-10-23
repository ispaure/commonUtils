# Docking workspaces

Docking, tab gestures, splitting, floating windows and native workspace menus.

Moving an existing dock to a different tab group explicitly detaches that dock
before tabifying it with the requested anchor. This preserves unrelated groups
on Qt 6.12 as well as earlier Qt versions.
Deferred header and docking callbacks use their QObject owner as timer context,
so deleting a workspace or dock cancels its queued callbacks.

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

## Drag and header owners

`drops.DropCoordinator` resolves eligible workspaces, placement and preview, then
revalidates eligibility before committing adoption. Both drag transports use this
same boundary; `headers.DockTabHeader` owns single-tab header controls and painting.
See [drop and retirement contracts](../workspaces.md#drop-resolution-and-pane-retirement).

Cross-workspace adoption captures source order/selection, both saved layouts and
floating geometry in an immutable `_DockTransferSnapshot` before changing Qt
ownership. The existing workspace names acceptance and rollback phases; `adopt`
retains guards, transfer flags, final signal publication and source cleanup.
Failed arrangement or destination registration restores the source without an
owner-change signal. Header refresh separately reconciles dock title controls
and native tab bars after checking the workspace's lifetime.
