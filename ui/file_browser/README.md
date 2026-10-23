# File Browser integration

`commonUtils.ui.file_browser.FileBrowser` embeds reusable browsing, selection,
previews, indexed search and size maps. Applications supply domain actions and
host navigation. Start with the [runnable browser example](../features/README.md#runnable-example-add-a-menu-action-to-a-browser).
For workflows and settings, see the [user guide](user_docs/README.md).

Deferred breadcrumb reveals are bound to the bar's Qt lifetime and ignore an
already-retired native scroll area. Range/layout callbacks during teardown must
not access deleted child widgets.

## Construction and navigation

The column view installs its preview before its model. On Qt 6.11+ it applies
the native preview visibility switch only after attaching a model, avoiding
Qt 6.12's null-model crash during construction. Earlier Qt versions retain
the preview host sizing fallback.

Filesystem and sorting models also route Qt's batched `multiData()` role requests
through their Python `data()` implementations. Native delegates therefore retain
custom filenames, recursive folder sizes and cached thumbnails on Qt 6.12.

To open a standalone browser at a specific folder, put commonUtils on the Python
import path, install PySide6, and run this minimal script. Replace the example path
with an existing directory:

```python
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser

app = qt.initialize_q_app()
browser = FileBrowser(Path("/path/to/folder"))
browser.resize(1000, 700)
browser.show()
app.exec()
```

Keep `browser` alive while the event loop runs. Its own close handler waits for
browser workers to finish; hosts embedding it in another window must handle that
window's shutdown as described below.

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
Built-in menu open/rename actions and queued inline renames retain paths and
resolve fresh model indexes when invoked. Removed paths and stopped browsers are
ignored; callback closures do not retain native persistent indexes past teardown.

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
subscription; cancelling one subscriber only stops in-process work when none remain.
When the host enables the persistent index coordinator, cancellation detaches the
view while submitted work survives. A host-provided `shared_activity` Qt signal
connects idle browsers to jobs started by another process. Cache-only views can
follow existing work without requesting a scan; explicitly paused views do not.

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
into a filesystem traversal. Hosts expose pause/resume through indexing methods;
the toolbar selects the displayed chart directly.

[Developer hub](../../docs/developer/README.md) · [UI overview](../README.md)

## Index and chart controls

The browser owns filesystem watches and a single-shot reconciliation debounce;
it creates no periodic polling timer. Index detail and refresh controls reflect
worker state. Hosts can continue to expose pause/resume through the indexing
methods without creating a hidden pause button. `open_storage()` remains available
for hosts that use the independent storage dialog.

Treemap and Radial selection flows from the toolbar into
`StorageView.set_chart_mode(0 or 1)`. The displayed chart stack is the source of
truth for cached results and stale-worker checks; no hidden combo box mirrors it.
Former `reconcile_timer`, `storage_button`, `index_pause_button` and
`chart_selector` attributes have been removed.

Default context menus include Pick Link Source for a single selected item and
Drop Link As/Cancel Link Creation when an application-local source is present.
`link_actions` owns the transient selection; `FileActions` runs exclusive link
creation on its existing worker and refreshes the destination through normal
reconciliation. Busy/stopping guards and close ownership match other file actions.
Link creation contracts belong to `filesystem/links/README.md`.

`FilesystemObject.browser_thumbnail_badge()` returns an optional short string for
an overlay at the top-right of a tile's thumbnail. It runs during painting, so it
must be cheap, bounded and dialog-free; archive parsing belongs in the thumbnail
worker, not this hook. The visible tile view repaints once per second for live
labels without invalidating cached covers. The refresh timer stops with FileViews.

Thumbnail caches and queued request/revision keys use `Path` objects internally.
Qt model lookups and the existing thumbnail-request signal convert to strings at
the boundary; completion and invalidation accept either spelling on Windows.

FileDragDrop routes local URL drops into FileActions.transfer, sharing paste's
worker, cancellation and refresh lifecycle. Its own QDrag avoids Qt deleting
source rows after an asynchronous move. Internal drags are identified within the
current process; external drops acknowledge CopyAction and preserve their source.
Qt columns install the controller through column_created as they are created.


### Host-managed directory navigation

`FileBrowser(..., directory_handler=callback, directory_boundary=predicate)`
lets a host route selected directories to another browser. Both callbacks receive
an absolute `Path` on the GUI thread and must be inexpensive. The handler returns
true when it consumes navigation (including refusal or an unlock prompt); the
regular browser retains its location. Hosts should defer UI replacement until the
current signal returns and own errors, credentials and replacement-view lifetime.
The boundary predicate is read-only: the filesystem model does not list or fetch
children beneath matching directories. It must not open dialogs or navigate.

Hosts may supply `column_navigation=False` to omit QColumnView entirely while
keeping list, thumbnails, details and storage modes at their established indices.
The column button is disabled and requesting mode 2 raises ValueError;
`views.columns` is None. The default remains True. This is an explicit host choice,
not a claim that every other mode has been verified on mobile. A consuming iOS
proof uses it to isolate a Qt 6.12/Python 3.15 column-navigation native crash.

Routing covers explicit locations, breadcrumbs, activation, tree expansion,
column navigation and storage/search navigation. Cached file activation routes
its parent directory before ordinary file launch. The shared browser knows
nothing about encryption or application backends. Use the host's trusted logical
location type when cloning a provider tab; raw filesystem locations cannot stand
in for decoded provider paths.

## Shared provider presentation

List, tile and column presentation is owned by `BrowserViews`; `FileViews` adds
local indexed storage charts. The local filesystem model supplies shared item roles
while retaining its watcher and existing file APIs. Provider browsing and pickers
use the same views through `ProviderEntryModel`. Arbitrary item identities and
custom properties are available through the UI-independent browse tree and its
Qt `EntryModel`. See the [item and provider contract](../resource-providers.md#shared-item-presentation)
for loading, identity, thumbnail, privacy and lifecycle rules.


Mobile consumers use [NativeBrowser](../native_browser/README.md), which presents
list/tile views over the same portable tree and provider-row conversion through
Toga, rather than importing Qt widgets. Backend-specific presentation stays separate
while source identities, metadata rows, revisions and mutation contracts are shared.
