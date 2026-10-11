# File Browser integration

`commonUtils.ui.file_browser.FileBrowser` embeds reusable browsing, selection,
previews, indexed search and size maps. Applications supply domain actions and
host navigation. Start with the [runnable browser example](../features/README.md#runnable-example-add-a-menu-action-to-a-browser).
For workflows and settings, see the [user guide](user_docs/README.md).

## Construction and navigation

Create QApplication first, then `FileBrowser(root, parent=owner)` and add it to
an existing layout or main window. The constructor accepts `services`,
`action_providers`, `folder_fields`, `calculate_folder_sizes` and
`index_settings_path` as keyword options. Prefer [Feature declarations](../features/README.md)
for new grouped integrations. Keep existing constructor arguments, signals and
established widget fields compatible.

`set_directory(path, navigation_root=...)` separates the initial location from its
navigation boundary. The one-argument API remains folder-scoped. Applications choose
Home/root defaults and new-tab destinations; these are not universal library policy.
`index_settings_path` selects refresh preferences, **not** an alternate SQLite cache.
See [index policy](user_docs/README.md#settings-and-their-effects).

## Selection and extensions

`selected_objects()` returns filesystem objects. `selection_changed(objects)`,
`details_loaded(result)` and `refreshed()` notify hosts. After mutations use
`refresh_item(path)` or `refresh()` as appropriate. Existing objects remain snapshots;
registry revisions cause browser models to re-resolve future objects.

Preview is optional in tiles/list, intrinsic to columns, and replaced by ranked
entries in storage views. Turning it off avoids automatic detail loaders;
`selected_object` remains available. Explicit `load(item)` displays details when
Preview is enabled. Keep `preview_panel`, heading/message/cover fields and existing
preview interfaces compatible for established consumers.

Panel/thumbnail providers return data from workers; action and activation handlers
run on the GUI thread. Controllers own expensive action jobs. File information,
preview cache invalidation and source/proxy selection mapping must continue to refer
to the original filesystem items, including after sort/view changes. See
[extension contracts](../../docs/developer/extension-points.md).

## Index and search lifecycle

Live file browsing and cached recursive metadata are independent. `open_search()`
returns the embedded IndexSearch panel, not a standalone dialog. Search and storage
read cached snapshots on workers and follow shared index updates. They do not launch
independent scans. Network locations disable indexing/search/storage and automatic
rich previews while retaining ordinary browsing and explicit opening.

Index policy is read per request. Explicit refresh validates the subtree; ordinary
navigation can use cached data or immediate-folder checks. Disjoint scan roots keep
independent jobs while SQLite serializes writers. Visible-folder priorities apply
within an existing scan root. Each tab retains its own selection/navigation and
subscription; cancelling one subscriber only stops shared work when none remain.

See [index persistence and migration](../../filesystem/index/README.md). Snapshot
owners must close readers when done, especially before removing temporary databases
on Windows. Do not close a shared cache while other views still use it.

## Shutdown and workspaces

`stop()` returns **true while workers are still finishing**. Ignore close while
true and retry on `idle`. `shutdown()` waits during final application exit. Retain
controllers and feature bindings as long as their jobs need them: browser stop does
not substitute for `binding.prepare_close()` (false means controller not ready).
See [initialization and shutdown](../../docs/developer/architecture.md#initialization-and-shutdown).

A [Workspace](../workspaces.md) may remove a worker-only tab from view while keeping
its hidden owners until idle. Close vetoes retain the tab, and whole-window shutdown
checks retired owners too. Dock groups and optional WorkspacePolicy govern transfer
and detached-window behavior; application destinations remain host-owned.

## Maintenance boundaries

Orchestration/selection is in `__init__.py`; views/model map source objects to
presentation; indexing/index_worker own lifecycle and subscriptions; storage/search
modules read snapshots. File/trash actions own confirmation and mutation integration.
These implementation locations explain maintenance responsibilities, not a guarantee
that every helper is a public API.

Keep current bounded chart reads (3,000 entries, four radial levels), stale-result
rejection and row/sector selection correspondence. Radial scene caching depends on
chart data, size, font and palette; selection/zoom reuse it. Do not turn a chart refresh
into a filesystem traversal. Hidden pause/chart selector objects are
not a reason to document visible controls that do not exist.

[Developer hub](../../docs/developer/README.md) · [UI overview](../README.md)
