# UI API reference

The `commonUtils.ui` package provides reusable cross-platform UI helpers with both **native** and **PySide6** backends.

Generic message boxes can be called directly through `commonUtils.ui`. When `use_pyside` is enabled, the package attempts to use PySide first and falls back to the native backend if PySide is unavailable or fails.

## Backends

### 📄 `__init__.py`

Provides the generic UI interface and lazy backend loading.

Currently available generic functions:

- `display_msg_box_ok()` — display an OK message box
- `display_msg_box_ok_cancel()` — display an OK/Cancel message box and return the user's choice

```python
from commonUtils import ui

ui.use_pyside = False  # This standalone example has no QApplication.
ui.display_msg_box_ok("Example", "Operation completed")

if ui.display_msg_box_ok_cancel("Example", "Continue?"):
    print("Continuing")
```

Set `ui.use_pyside` to control whether supported generic functions should attempt
to use PySide first. Its default is True. When PySide is installed, create a
QApplication before calling a generic dialog, or use the native backend as above.
Qt may abort the process if a widget is created without an application; Python
exception fallback does not make that safe.

The individual backends are also lazily available as:

```python
ui.native
ui.pyside
```

### 📄 `native.py`

Provides lightweight message boxes without requiring PySide or another Python GUI framework.

Platform-specific implementations use:

- **Windows** — native Windows message-box APIs
- **macOS** — AppleScript
- **Linux** — `kdialog`, `zenity`, or `xmessage`, with a console fallback

The native backend currently provides OK and OK/Cancel dialogs.

### 📁 `pyside/`

Provides the more complete PySide6 UI toolkit used for building application interfaces.

This backend requires the optional `PySide6` dependency and an existing
QApplication before creating any widget or showing a message box. The PySide
snippets below assume the application has performed the setup shown next.

```python
from commonUtils.ui import pyside

# Legacy commonUtils.pySideUtils imports resolve to this same module.
# Implementations are grouped into application, widgets, windows, messages and progress.
q_app = pyside.initialize_q_app()  # Once per process; retain this object.
```

Available helpers include:

- `Window` — base dialog or main-window abstraction
- `button()` — create a push button and connect it to a function
- `button_open_win()` — create a button that opens another window
- `Label` — label wrapper
- `LineEdit` — text-entry wrapper with optional password mode
- `create_checkbox()` — checkbox creation
- `create_frame()` — framed UI panel
- `create_grid()` — grid-layout creation
- `create_scroll_area()` — scrollable content area
- `create_scroll_area_grid()` — scrollable grid area
- `create_size()` — create scaled `QSize` values
- `set_font()` — apply the common UI font settings
- `Palette` — palette helpers, including dark and navy palettes
- `initialize_q_app()` — initialize the PySide `QApplication`

#### Message Boxes

The PySide backend provides several configurable message-box combinations:

- OK
- OK / Cancel
- Ignore / Abort
- Yes / No
- OK / Help

Message boxes support configurable icons, dimensions, and callback functions where applicable.

```python
from commonUtils.ui import pyside

pyside.display_msg_box_yes_no(
    "Confirmation",
    "Continue?"
)
```

#### Progress Bars

`ProgressBar` and `ProgressBarWindow` provide reusable progress UI.

A progress window can be created with:

```python
from commonUtils.ui import pyside

progress = pyside.display_progress_bar("Processing")
```

The progress-bar implementation supports updating progress and displaying status text while an operation is running.

## PySide Application Setup

Create one QApplication per process, as shown above. In an existing Qt application,
reuse its application rather than call `initialize_q_app()` again. The helper
configures Fusion style and applies platform-specific setup where required.
Standalone windows also need an event loop (`q_app.exec()`); see the complete
[browser example](../FEATURES.md#runnable-example-add-a-menu-action-to-a-browser).

## Dependency

Most of `commonUtils.ui` does not require PySide6 when the native backend is used. Install `PySide6` only when the PySide-specific functionality is needed.

```text
PySide6
```

Because the backends are lazily imported, accessing the native UI does not unnecessarily import PySide.


## Background work and downloads

Use [the workflow recipes](../RECIPES.md) for complete examples of
`OperationProgress`, safe dialog closing, per-item batch cancellation, stream
progress and verified download prompts. The synchronous legacy progress widgets
only display progress; callbacks must use an explicit worker to avoid blocking Qt.
The generic worker lives at `commonUtils.ui.operations.Operation`.

For automatic background work that should not change the layout, pass
`show_progress=False` to `OperationProgress.start()`. Completion, progress reporting
and `request_cancel()` still work; callers provide their own cancellation control.
The default continues to show the progress widget.

## Reusable file browser

See [Reusable file browser](file_browser/README.md).

## Reader controls

`reader_menus.ReaderMenus` supplies File/Edit/View/Navigate menus and filtered
recent files for an application's format-specific readers. `reader_chrome`
supplies matching line icons/buttons, elided single-line titles/status, shared
spacing and a fullscreen controller that tracks native window-state changes and
restores maximization. These helpers do not load content or determine how pages
turn. See [feature authoring](../FEATURES.md) for the contracts.

## Markdown reader

See [Markdown reader](markdown/README.md).

## Plain-text files

`from commonUtils.ui.text_editor import TextFileEditor` provides an embeddable UTF-8
file editor (`TextFileEditor(path, parent=None)`). Its `save()`, `reload()` and
`can_close()` methods support explicit atomic saving and unsaved-change prompts.
It preserves BOM/newline conventions and refuses to overwrite external changes.
Hosts should call `can_close()` before destroying it. The `saved(path)` signal
allows consumers to refresh configuration. It renders text directly without
interpreting INI sections or keys.

## Shared navigation settings

`commonUtils.settings.settings_path()` locates `ui/settings.ini` beside the browser
package. Logistics exposes this file under **Settings → commonUtils** using the
plain-text editor. Saves apply to existing comic readers on the next wheel event.
`get_setting(section, key, default, minimum=None, maximum=None)` reads bool, int,
float or string values using the default's type (bounds are keyword arguments).
`get_wheel_navigation_settings()` returns immutable validated wheel preferences.
Both accept a keyword `path` override for other hosts/tests. Missing, unreadable,
malformed or invalid settings use defaults; reads never rewrite the INI. File
identity timestamps cache parsing and invalidate it after edits.

The `[WheelNavigation]` defaults are `immediate_notches=true`, `sensitivity=20`
(range 1–100), and `cooldown_ms=250` (range 0–2000). Each vertical angle-only wheel
event with no scroll phase turns one page regardless of delta magnitude. Smooth
pixel/phase events accumulate to 60 pixels or 120 angle units divided by sensitivity,
with a cooldown to avoid bursts. Disable immediate notches to apply the smooth
threshold and cooldown to all wheels. Loading, modifiers and modal dialogs still
block navigation. These preferences affect discrete page navigation, not ordinary
file-browser list scrolling.

`FileBrowser(..., calculate_folder_sizes=False)` skips automatic recursive size/count
scans for large roots. `set_folder_sizes_enabled(True)` resumes automatic totals;
disabling requests cancellation and drops displayed totals. Logistics now enables
this by default, with a Background sizes pause/resume checkbox. Browsing a different
location supersedes the previous job and prioritizes that subtree. Refresh explicitly
reconciles saved metadata. Directory listings and feature actions remain available.

`scan_folders()` preserves its public name and FolderStats return shape, but now
uses the same SQLite scanner as search and storage. Schema v2 adds persisted folder
bytes, file/subfolder counts, extension counts, completeness and aggregate timestamps.
The worker first publishes cached totals, periodically publishes partial aggregates,
and validates every descendant's metadata before declaring sizes final. Partial sizes
use a ≥ marker and explicit status; cached values are identified while checking.
Only displayed model parents are invalidated, avoiding accidental loading of every
indexed folder on the GUI thread. The storage treemap consumes these saved aggregates
rather than independently walking the filesystem.


## Document workspaces, discovery and process execution

`commonUtils.ui.workspace.Workspace(factory)` hosts cooperative document views in
native Qt dock tabs. Views may provide `view_title`, `title_changed`, `idle`, and
`prepare_close()`. Each view owns its state. Tab headers share their group's width,
with a close button on the left of each tab and a small **+** after the tabs.
Right-clicking a header offers **Close tab**. New/close keyboard shortcuts remain
available, including when no tabs are open. Native tab dragging remains supported.
The former action toolbar is removed; `detach_active()`, `reattach_active()`,
`arrange(dock, placement)` (left/right/tabs), and `adopt(dock)` remain available
in code for floating, splitting, combining and transferring existing views.
Empty workspaces provide a full-size native dock anchor and a **+** button;
the anchor disappears after a real view returns. `reattach_active()` returns a
floating view without requiring a drag, even when no tabs remain docked.
Detached views also accept native top-edge drops. Once Qt finishes the drop,
the returning view joins the existing tab group (or fills an empty workspace)
instead of leaving a separate top split. Left/right docking remains available.
New tabs are grouped only with docked views, leaving detached views independent.
Call `prepare_close()`
before destroying an embedded workspace; it waits for all views' workers.

`commonUtils.directory` supplies immutable `Entry`/`Snapshot` metadata,
case-insensitive partial name search, and `storage_totals()`. `DirectoryCache`
persists completed and partial indices in SQLite, without entry/root count limits.
`directory_index_path()` defaults to:

- macOS: `~/Library/Application Support/commonUtils/Cache/directory-index.sqlite3`
- Windows: `%LOCALAPPDATA%/commonUtils/directory-index.sqlite3`
- Linux: `$XDG_CACHE_HOME/commonUtils/directory-index.sqlite3` (default `~/.cache`)

One database holds every indexed root and recursion scope. SQLite can also create
`-wal` and `-shm` files while connections are open; a `directory-index.lock` file
serializes writers across windows/processes. No source file contents are stored.
`DirectoryCache(database=path)` selects a different database for another host/test.
The index storage folder is excluded from its own scans. Root symlinks retain
lexical result paths; nested symlinks/junctions are listed without traversal.

Completed folders retain resumable checkpoints. Metadata is written in batches of
512 entries; commits occur after 4,096 entries or roughly half a second, with an
explicit flush on cooperative cancellation. An interrupted folder must be enumerated
again. Cancelling preserves the completed-folder checkpoints and last complete index. `get()` resumes pending discovery before revalidating previously scanned
folders/files, so missing branches become searchable first. It validates before reuse
and reconciling additions, removals, replaced links and changed metadata. Unreadable
or changing folders produce a clearly marked partial snapshot and remain retryable.
`get(..., refresh=True)` discards pending work and rebuilds; `clear(root)` removes
overlapping indices. `invalidate(root)` requests an update on the next operation
without blocking the GUI thread. Cancellation is cooperative between filesystem
calls, and also interrupts long SQLite queries and waits for another writer.

Snapshots expose a read-only sequence of entries backed by SQLite. Iteration and
storage aggregation stream rows; name filtering/paging runs in SQL. Existing open
snapshots remain consistent during rebuilds/clears via SQLite read transactions.
These readers can retain WAL data until their result windows release old snapshots.
The database reuses freed space rather than imposing a fixed entry limit.

Search shows 500 results per page, with all matches available through Previous/Next.
Column sorting applies to the entire match set before paging.
Inside a `FileBrowser`, Search and Size Map read cached snapshots on workers and
follow shared background index updates. Size Map is the fourth browser view,
with Treemap selected by default and a Radial option showing up to four levels
(maximum 3,000 radial chart nodes; gaps represent omitted entries). Both use saved sizes, normal breadcrumbs/history,
file previews and context actions; they never launch an independent filesystem scan.
Treemap loads only immediate entries and their cached folder totals. Radial detail
is fetched on demand. Child lookups use the parent index and cached snapshot entry
counts are lazy, so displaying a chart does not require a whole-generation count.
Partial charts are labeled and refresh as indexing commits progress. The legacy
Storage dialog API remains available; its **Refresh view** only reloads saved sizes.
Rebuild/clear controls are hidden in managed dialogs.
Standalone legacy dialog hosts retain their scan/resume/rebuild APIs and controls.
The index path appears in the snapshot status tooltip. Dialogs participate in
browser cancellation/shutdown, and snapshot
dates/partial-state labels distinguish indexed results from a live filesystem view.
Browser modification dates use `filesystem.format_datetime()` consistently.

`network_filesystems` identifies UNC paths, mapped Windows network drives and
network mount points from local mount metadata. Browsers disable size maps,
indexing, scans, indexed search and automatic cover/metadata extraction on these
locations. Shared scan exclusions also omit network mounts nested under a local
scan root. Normal file browsing and explicit file opening remain available.
Windows filesystem browsers put the drive/network-location menu in the first
breadcrumb; scoped folder browsers keep their existing navigation boundary.

`ui.read_aloud.ReadAloud` starts from the visible reading area, or the reader's
explicit page-start provider. It highlights individual words using native speech
events where available and estimated timing otherwise. Back/forward controls
estimate a 15-second jump from speech progress and rate, preserving pause state.
`ui.icons` renders Python icon painters into native Qt pixmap icons and refreshes
bound controls when the palette changes, avoiding Python icon-engine ownership
during native window teardown. The shared docking workspace hides the final
attached browser tab's close button while allowing documents to close at any time.

Browsers in one application share a worker for the same database and location.
Each tab can pause its own subscription; the last subscriber cancels the worker.
Cached search results and folder sizes remain visible when paused. Other processes
still serialize through the database writer lock. The browser status reports the
current phase/folder, saved entry count, entries processed in this run, average
processing rate, and elapsed
time. Saved counts are shown before loading folder totals. Unknown discovery
totals are never presented as a percentage. Navigating into a partially indexed
ancestor reuses its saved subtree checkpoints; completed folders need no new
enumeration. Interrupted folders are still enumerated again because directory
iteration positions cannot safely be persisted across filesystem changes.

The scanner fetches pending folders in batches and prioritizes unvisited folders.
Folder identity checks use one metadata call. Progressive totals recompute changed
folders and their ancestors from immediate entries and persisted child totals.
A full aggregate pass streams unsorted file rows and sorts directories alone.
`DirectoryCache.last_metrics` exposes metadata, database-write, aggregation,
validation and checkpoint seconds plus bounded checkpoint counts for diagnosis.
Progressive aggregate refresh intervals adapt to their computation cost; unchanged
aggregate rows are not rewritten. Source metadata, paths and natural-order keys
remain stored for validation and paging; source file contents are never indexed.

`commonUtils.ui.process_runner.ProcessRunner` executes argument vectors through
QProcess with incremental UTF-8 output, actual exit status, cooperative cancellation,
and optional whole-process retries. A process-specific parser returns
`ProcessUpdate` objects for stats and internally managed retry attempts.
`ProcessProgressWindow` presents these signals without owning command-specific
logic. `open_process()` retains modeless windows, including their final result;
application hosts call `prepare_close_all(retry_close)` before closing. Success
requires a normal zero exit; cancellation and failed starts remain distinct outcomes.


## Shared temporary storage

`commonUtils.storage.cache_directory()` resolves/creates the persistent cache
area using macOS Library/Application Support/commonUtils/Cache, Windows LOCALAPPDATA,
or Linux XDG_CACHE_HOME (with ~/.cache fallback; relative XDG paths are ignored).
`temporary_directory()` creates disposable workspaces under macOS
Library/Application Support/commonUtils/Temp, or the persistent area's Temp subdirectory on
Windows/Linux. `temporary_workspace()` returns a
private, automatically cleaned TemporaryDirectory there. Use `create=False` for
side-effect-free path resolution. Persistent caches are never deleted on exit.
Destination-side staging remains beside the destination for atomic replacement.

On first use of the default SQLite index at its new location, a transactional
SQLite backup migrates the former location, including
committed WAL data and partial checkpoints. The original remains for recovery and
older running applications. Existing canonical caches are never overwritten;
explicit `DirectoryCache(database=...)` paths are not migrated.
On macOS, migration prefers Library/Caches/commonUtils's index and falls back to
the older index directly under Application Support/commonUtils.

## Opt-in Slate appearance

`from commonUtils.ui.theme import apply_theme` then `controller = apply_theme(app)`
opts an existing QApplication into the shared Fusion palette and stylesheet.
Imports and other commonUtils consumers keep their current appearance. Modes are
`system` (default), `light`, and `dark`; `controller.set_mode(mode)` changes the
appearance immediately, and system mode follows Qt's OS color-scheme notifications.
`[Theme] mode=...` in the shared settings INI supplies the startup preference.
Logistics opts in at launch and offers a live Appearance selector in commonUtils
settings. The INI editor retains explicit saving and existing wheel preferences.
Selected tabs combine a contrasting surface, bold text and palette accent underline,
including workspace headers and native grouped dock tabs. Standard selection pairs
and ordinary/muted text meet WCAG 4.5:1 contrast in both palettes.

## Indexed search in the browser

See [Indexed search in the browser](file_browser/README.md).

## Selection preview

See [Selection preview](file_browser/README.md).

## INI settings editor

`commonUtils.ui.ini_editor.INISettingsEditor` displays section tabs and one row
per key, with a Source tab and explicit saves. It inherits the text editor's
unsaved-change protection. Ordinary INIs use string fields; pass `typed_keys=True`
for typed validation, boolean checkboxes and dropdowns. Applications supply the
path and decide how saved changes apply. See the
[configuration guide](../configuration/README.md) for conventions and a complete
embedding example.

## Reusable code editing

See [Reusable code editing](code_editor/README.md).

## Reusable docking workspaces

`commonUtils.ui.workspace.Workspace` owns dockable tabs, full-window dragging,
left/right splits, grouped tab headers, transfer between compatible workspaces,
and cooperative closing. It imports no Logistics features. Supply a factory
returning a QWidget, optionally exposing `view_title`, `title_changed`,
`prepare_close()` and an `idle` signal. A view may set `can_retire` to retain its
worker owners while its visible tab disappears immediately.

Set `allow_new_tabs=False` for externally created documents and
`keep_one_tab=True` to protect the final attached browser tab; floating panes can
still close. `dock_group` restricts transfers to compatible hosts. Override
`reveal_for_drop(global_point)` if dragging should reveal an application-specific
hidden destination. Window dragging and drop placement stay generic; feature
selection, dirty-document prompts and retained original window ownership belong
to the application. `document_host.py` supplies optional hosting and original
window lookup for reusable readers that also work standalone.

Hosted reader close buttons and delayed worker callbacks should use
`document_host.close_document(window)`: embedded documents receive their own
close event and retain save/cancel decisions; independent windows close normally.
Views with no document-close veto may opt into `close_in_background = True` to
remove their workspace tab immediately, before cooperative shutdown begins.
Their owners stay alive until `prepare_close()` succeeds after an `idle` signal.


## Passive archive contents

See [Passive archive contents](archive_view/README.md).

## Shared document and navigation contracts

Optional `document_host` routing embeds a reader/editor in its application's host
or opens it standalone. `request_document_close(window)` returns CloseOutcome:
ACCEPTED, VETOED or PENDING. Owners may implement request_close and an idle signal;
they handle unsaved prompts and asynchronous retirement themselves. A host must
retain pending owners and retry after idle rather than inspect private fields.

`outline.OutlineEntry(id, label, target, depth=0)` carries an opaque navigation
target. OutlineList and OutlineTree populate navigation widgets with set_entries;
items_by_id retains stable selection handles. They provide no filesystem actions.

Reader chrome supplies reading_spin and show_reader_popup with caller-selected
ranges, callbacks and alignment. text_commands.wrap_selection provides one undo
step and UTF-16 cursor accounting with explicit selection/format policy.
entry_views provides selection and sorting mechanics without path semantics.

## Shared result presentation

NotificationCenter retains bounded Notice events, deduplicates IDs and tracks
acknowledgement. Toast renders plain text and an optional details action for a
bounded interval. Applications choose native delivery, event IDs, destination
badges and persistence; these widgets never decide whether an operation is safe.

ResultWorker captures callback result/error under noninteractive logging. Owners
consume them after finished and retain workers until retirement. Cancellation
boundaries and error formatting can be supplied by the caller. Operation retains
its compatibility completed signal; use OperationProgress for finish-safe delivery
with progress and cancellation controls.

Workspace tab bars use horizontal dragging to reorder panes. Drag outside the
tab bar to detach and move the whole pane, then drop to tabify or split. The
workspace keeps its dock order synchronized with native tab order so indexed
close actions and document lists refer to the visible tab.


Floating `WorkspaceDock` panes use regular native window flags, including
minimize/maximize controls and no transient parent. The inner tab header still
supports dragging and double-click reattachment. Their cooperative close handler
and `WA_QuitOnClose=False` preserve the document/worker lifecycle.
