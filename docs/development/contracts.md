# Integration contracts

## Hosted Qt painting

Widget paint handlers must end every locally owned QPainter before returning,
using a context manager or try/finally. Do not rely on immediate Python object
destruction: the Qt 6.12 iOS/Python 3.15 consumer exposed overlapping painters
when editor gutters and browser breadcrumbs relied on local-variable cleanup.
Mobile Qt admission is an explicit QApplication host contract documented in
`runtime/platform/README.md`; it does not admit desktop side effects.

Use the module paths in the [API guide](public-apis.md). The library imports its
subsystems through ordinary Python packages. Importing the root loads no GUI,
installs no custom import hooks and initializes no subsystem.

Logistics pins commonUtils as a Git submodule. Ally Tools uses that same checkout
through its Logistics host. Blue Hole vendors the library under its own namespace;
its modules and registries are independent of a standalone commonUtils import.
Validate each consumer before updating its pinned or vendored revision.

## Data and behavior

Markdown embeds retain the widget's explicit navigation/edit/save entry points.
Document identity and byte/rich-import baselines now live in
`viewer.document_state`; hosts migrate direct private `_loaded_path` and
`_source_bytes` assignments to that declared owner. Source editor text and undo
history remain editor-owned. See [Markdown ownership](reference/ui/markdown/markdown.md#internal-ownership-and-embedding-contracts).

Browser adapters use `DirectoryCache.shared_source()`, `follow_shared_source()`
and `shared_scan_completed()` for shared scan bookkeeping. The cache owns its
lock, source mapping and session completion markers; these calls do no SQLite I/O.
Following a scan does not mark it complete.

Index scan instrumentation reads transient counters from `cache.active_operation`
inside the writer operation. That object is detached on success/failure;
`last_metrics` remains available afterward. Saved database formats and scan,
reconciliation and snapshot-lifetime contracts are unchanged. See
[index state ownership](reference/filesystem/index/index.md#state-ownership).

File instances retain their original path and cached metadata. Registration changes
affect future resolutions. Feature bindings filter captured selections by accepted
types; handlers still validate current state before mutation. Read
[extension points](extension-points.md) before changing these interfaces.

Shared settings live at `ui/settings.ini`. Readers use defaults for invalid/missing
values and do not rewrite configuration. INI key changes require updating consumers
and a deliberate migration of saved values. See [configuration](reference/configuration/configuration.md).

Cache/data locations and launcher lookup are observable behavior. SQLite schema
changes need writer locking, rollback, old-reader consistency and preservation of
resumable checkpoints. Consumers use Entry/Snapshot rather than database IDs. See
[storage](reference/filesystem/storage/storage.md) and [indexing](reference/filesystem/index/index.md).

Text encodings, BOMs, line endings, conflict checks and unchanged-byte preservation
are format-specific contracts. Atomic replacement is not a writer lock. Preserve
explicit source editing when a formatted editor cannot round-trip a document.

## Platform and lifecycle

Windows/macOS/Linux support does not make every native adapter portable. Speech,
trash, terminals, network detection and external tools need platform validation.
The checked-in CI selects Python 3.12.2; the application owns dependency pins.
There is no formal release/version policy or tested universal dependency range.

Retain owners through cooperative shutdown and respect document close vetoes.
Workspace view factories may return `None` after a cancelled open; `add_view`
then creates no dock or tab.
`initialize_q_app()` installs the Windows DPI-size policy; custom QApplication
hosts opt in through `install_window_dpi_scale_fixer()`. The helper observes native
messages without consuming them and only repairs normal-window client QSize
drift. Keep Qt's DPI awareness and display scaling enabled. See the
[backend guide](reference/ui/pyside/pyside.md) for lifecycle and validation limits.
Browser `stop()` returns true while busy; controller `prepare_close()` returns
false while not ready. See [architecture](architecture.md#initialization-and-shutdown).

## Updating consumers

Review imports, arguments, return values, data formats and lifecycle together.
Run shared regressions and each affected consumer's tests, update their imports
and documentation, and then update the pinned or vendored source. Keep domain
workflows in the consuming application.

[Developer hub](development.md)

## Layered configuration and typography

Registered defaults/personal INI paths enable sparse, validated overrides without
changing unregistered consumers. Reads do not create files; malformed overrides
remain untouched. Reset removes an explicit personal field, never a software
schema field. Atomic saves reject concurrent edits. Hosts own migration and paths.
See the configuration guide for the API, and `ui/styling.md` for live font roles,
weak widget binding, optional application-font opt-in and settings navigation.
Shared font-size settings use a 96-logical-DPI reference. Convert settings through
`ui.appearance.typography.point_size()` before assigning Qt point sizes, and use
`setting_size()` when saving or incrementing a rendered font size. Do not persist
the platform-adjusted QFont point size or disable Qt's native display scaling.

## Grouped UI imports

See [UI module organization](reference/ui/ui.md#module-organization) for canonical
package paths. Flat forwarding modules for workspace, task, reader, settings and
appearance implementations have been removed. Update imports, deferred dotted
references and mock patch targets to their owning package, for example
`commonUtils.ui.workspaces.workspace_drag` and `commonUtils.ui.appearance.styling`.
Modules import relatively within the library, so vendored namespaces retain their
own classes and registries without installing import finders or standalone aliases.
Importing a group alone does not import Qt. Existing guide URLs and
`ui/settings.ini` remain available.

Merge widgets and hosts import the data model directly from `persistence.merge`;
the former `ui.code_editor.merge_model` shim has been removed. Directory-cache
writers call `filesystem.index.schema.initialize_schema()` directly under their
existing writer lock; the private `_schema()` forwarding method has been removed.
Persistent formats, migration and cancellation behavior are unchanged.

Browser hosts select Treemap/Radial through the view selector; embedded storage
components may use `StorageView.set_chart_mode()`. The former hidden browser
buttons, storage chart combo box and unused periodic timer have been removed.
Pause/resume remains an indexing operation, and independent storage dialogs retain
cooperative shutdown. Watcher notifications and explicit refresh still schedule
index updates through the reconciliation debounce.

XML text/attribute escaping uses the standard-library HTML escaper with explicit
XML attribute entities. Portable file-type discovery does not import SAX's URL
and native proxy adapters; mocked platform tests reject networking imports too.

## Virtual resources

[Provider contracts](reference/ui/resource-providers.md) describe the generic directory,
archive and Markdown storage boundaries. Virtual paths are identifiers, not an
invitation to open local files. Consumers own backend selection, credentials,
provider lifetime and private-content policy.


Mobile staging defaults to clean Python sources. The `stage(..., allow_dirty=True)`
API explicitly permits local development snapshots, copies only tracked Python
sources, and records `commonUtils_dirty` in the source manifest. Consumers must
propagate this flag into their release/evidence checks; a local snapshot does not
certify a committed source revision.

### Shared browser presentation

`runtime.browsing` contains portable item snapshots and ancestry without UI or
filesystem imports. Qt models expose these entries through shared roles; regular
and provider browsers use the same `BrowserViews` for list, tiles and columns.
Filesystem watching, indexing and local actions remain in the local adapter/host.
Providers retain workers through cancellation and use RAM thumbnail caches. See
[shared item presentation](reference/ui/resource-providers.md#shared-item-presentation).
Native mobile list/tile views consume the same snapshots, with shared query/sort
projection, bounded recursive provider search and navigation history. Consumer adapters own local, crypt and remote I/O.

## Resource import migration and retained lifetimes

Use `runtime.resources` submodules and `ui.resources` adapters listed in the
[API map](public-apis.md#resource-and-dialog-owners). There are no forwarding
modules for the removed flat resource paths. Native message boxes use ordinary
`ui.native.dialogs` package imports; do not load a neighboring `native.py` file
or recreate a synthetic dialog module. Vendored imports retain their own namespace.

Provider path validation, Qt resource operation retirement and native browser
thumbnail/task retirement have separate owners. Retain provider leases until the
corresponding close operation finishes. A stale callback must not publish after
a provider/session generation changes. Transfer publication state remains explicit
when source cleanup fails; an exception does not imply destination rollback.

## Search and format owner migration

Search imports moved to `search.names`, `search.providers`, `search.indexed`, `search.qt_text` and `search.files`; see [search contracts](reference/search/search.md). Desktop matcher offsets and regex syntax are unchanged. Markdown imports use `formats.markdown.{properties,images,wiki,file}`; the package still exports property helpers. String tables use `formats.tables`, preserving Cell/Row/Spreadsheet methods.

Atomic persistence, filesystem information and feature declarations retain their package exports; implementation and mock targets now live in `persistence.atomic`, `filesystem.objects` and `ui.features.declarations`. Legacy print logging callers use `runtime.diagnostics`; UI helpers raise ordinary errors rather than exiting the host process. Personal Dropbox discovery belongs to Logistics, retaining its existing paths.
