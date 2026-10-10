# File browser maintenance

`FileBrowser` is the reusable host; Logistics supplies feature behavior through
extensions. Keep existing constructor arguments, methods, signals, widget fields,
and imports compatible. File handlers may also be used outside Logistics.

## Responsibilities

- `__init__.py`: orchestration, extensions, selection/detail work, indexing lifecycle.
- `views.py`, `tiles.py`, `columns.py`: view modes and source/proxy selection mapping.
- `model.py`: filesystem objects, cached totals and sorting by actual bytes.
- `preview.py`, `details.py`: optional selection pane, responsive cover, field display.
- `index_worker.py`: per-location shared work and independent tab subscriptions.
- `status.py`: path-free progress formatting, live elapsed time, one workspace line.
- `index_search.py`: cancellable paging of cached names, with no filesystem scan.
- `storage_view.py`: immediate-child treemap; bounded radial hierarchy on demand.
- `file_actions.py`, `editing.py`: clipboard operations and names; preserve source indices.
- `trash_actions.py`: removal confirmations, system trash and explicit permanent fallback.
- `search_columns.py`: responsive Name-first layouts for inline/dialog search results.
- `navigation.py`, `controls.py`: breadcrumbs, history and presentation controls.

The index backend is separated into `commonUtils.directory.reader` (immutable
SQLite readers), `directory.schema` (migration, record interning and membership),
`directory.store` (scan scheduling/checkpoints), `directory.reconcile` (targeted
completed-index updates), `directory.totals` (incremental
aggregation), and `directory.order` (natural ordering). Reader/order
imports remain available from `directory.store`. Public access uses
`commonUtils.directory`.

## State and ownership

Widgets and selections belong to the GUI thread. Panel loaders, filesystem work,
and database queries run in workers. Closing cooperatively stops workers before
Qt owners are deleted. Sharing a scan does not share selection/navigation state;
cancelling one tab unsubscribes it, and only the last subscriber stops the scan.
SQLite serializes writers across processes. Independent read transactions keep
older displayed snapshots valid while generations are replaced or pruned.

`set_directory(path, navigation_root=...)` separates an initial folder from its
navigation boundary. The original one-argument API remains folder-scoped.
Logistics uses the filesystem root for its default page, starts at the user's home
folder, and indexes that visible scope; creating the page does not launch a `/`
scan. Windows defaults to C: (falling back to the home drive if unavailable) and
provides a drive selector. New tabs in an unconstrained page start at Home and
retain filesystem navigation. Explicitly opened pages/windows and explicitly
scoped tabs retain their folder bounds. Starting at home does not add a synthetic root visit
to Back history.

Cached chart paths missing from Qt's live model activate directly by path. When
an explicitly opened hidden folder needs it, the live model temporarily enables
hidden entries in that subtree, restoring the original filter on leaving it.

Preview is enabled by default in tile/list views and starts at roughly 30% of the
splitter width (minimum 220 px). It shows selections or current-folder properties
when nothing is selected. Users may resize it or switch it off. Column view always
shows selected-file details in its native final column, matching the preceding
column width; selecting folders continues the folder trail. Its toggle is hidden.
Storage charts never show details previews: their right pane lists files and
folders largest first. Radial rows nest the loaded descendants; clicking a deep
sector expands its ancestors and scrolls to its matching row. Percentages use the
current root total at every level. The radial loader shares its 3,000-entry budget
breadth-first across siblings and reserves room for each of its four rings, so a
large early branch cannot consume the entire chart. Omitted entries leave gaps;
zero-byte folders have no area and incomplete indexed totals can leave branches
unrepresented until the index is repaired. Double-click a folder to explore deeper. Treemap and radial have separate toolbar buttons under
Storage. Their old `chart_selector` API remains available as a hidden widget.
Disabled previews do not start selection detail loaders. Existing `preview_panel`,
`heading`, `message`, `cover`, `tabs`, `preview`, `load`, and selection signals remain
available. Explicit `load(item)` still displays requested details when Preview is
enabled, and `selected_object` remains available when automatic previews are off.
The INI setting `[FileBrowser] preview_enabled` supplies new-tab defaults.

The magnifying-glass toolbar button toggles inline search, hidden initially.
The search bar sits below navigation in the file-list panel, alongside an X that
clears the query and closes search. Escape and the toggle also close it; Ctrl/Cmd+F
opens and focuses it. `open_search()` returns the embedded IndexSearch panel;
there is no standalone search dialog.
Opening a search-result folder keeps the query and searches that folder's
descendants. **Show in browser** explicitly exits search and locates the result.

Navigation and controls share one toolbar row. The inline **Size** slider follows
the breadcrumbs and immediately precedes View; it adjusts tiles, list icons and
column icons. Overflowing breadcrumbs keep the current folder visible and compact
the root shortcut. Layout-derived minimum sizes keep split panes from overlapping
when the window shrinks. The workspace footer is outside the bordered view
panes; cached-only reads do not show scan activity.

Workspace tab dragging uses explicit left/right drop zones and a center tab-group
zone (`commonUtils.ui.workspace_drag`). Closing a worker-only browser tab removes
it from the visible layout immediately; the workspace retains its hidden dock in
`_retiring` until its owners report idle. A feature close refusal keeps the tab
visible. Whole-window shutdown checks both visible and retired owners.
Dragging an attached tab shows a full-pane image; detached headers retain Qt's
native window movement and docking behavior.

Storage refreshes carry a root/mode/index-revision identity. Repeated mode changes
reuse loaded data and obsolete results are discarded. Immediate child reads and
rows are capped at 3,000, while saved root totals remain accurate; the view labels
this limit. Index progress uses saved file/folder aggregates rather than counting
every indexed entry. Unchanged totals do not rebuild models or details, and fresh
folder details replace existing presentation only once ready.

Filename search ignores case, including Unicode case folding. Bare space-separated
terms must all occur, in any order. Quoted phrases keep adjacent word order, treating
whitespace, underscores and hyphens as equivalent separators; punctuation and
wildcards otherwise remain literal. Unfinished quotes act as phrases during live
typing. SQL and detached snapshots share these rules in `directory.search.py`.
Phrase normalization is a SQLite scalar function at query time, so existing saved
names need no migration; unquoted keyword queries remain SQL substring predicates.
Search results give Name the remaining width, keep Type/Size sized to their
contents (capped at 130/110 px), and give Path roughly 27% of the view, up to 300 px.
Users can resize Path manually. Elided values have complete text in tooltips.
Names use a slightly stronger font weight; paths use the theme's muted color.

## Removing files and folders

Right-click selected items and choose **Move to Trash / Recycle Bin…**, or use
the platform Delete shortcut while a file view has focus. Delete inside a text
field still edits text. The confirmation defaults to Cancel and lists selected
names, with full paths under Details. Folder selections include their contents;
duplicate/parent-and-child selections are processed once.

`QFile.moveToTrash()` delegates to the system on macOS/Windows and the supported
freedesktop trash implementation on Unix. The browser does not assume a network
volume supports trash. If the operation fails, the item stays in place, errors
are available under Details, and **Keep items** is the default. Users may instead
choose **Review permanent deletion…**, then explicitly confirm a second warning
that the files/folder contents cannot be recovered through the app. A failed
trash operation never silently invokes permanent deletion.

`commonUtils.file_removal` provides snapshot plans and worker-safe execution.
Filesystem/mount roots are refused; item identity and parent resolution are
rechecked immediately before each operation. Symlinks are removed themselves,
without recursively following their targets. The shared operation UI cancels
between items and prevents conflicting mutations. Completed removals refresh
affected folders, invalidate previews, and participate in the browser's existing
worker shutdown lifecycle. Permanent removal can partially complete before a
permission/IO error; there is no application-level undo for that operation.

The shared status line and tooltip contain phases/counters, never scanner paths or
tab titles. Processed counts include discovery and validation operations, not a
claim of unique files; rate is the average over the run. Elapsed time continues
updating while the worker is busy with SQL, and supports seconds, minutes and hours.
The stable prefix and counters precede the changing phase. Browser size updates
read totals only for the current folder and its immediate child folders; each saved
total still includes all descendants. Full `scan_folders()` results remain available
to existing callers; the browser opts into `visible_only=True`.

## Event-driven index updates

Initial scans and partial resumes discover missing branches before verification.
Each discovery pass attempts a folder at most once: continuously changing folders
remain partial instead of looping. A finished attempt stays idle even with unreadable
or unstable folders; **Refresh index** retries them. Recorded folder failures are
preserved across parent updates and app restarts. Automatic resume skips these
failed branches while continuing unfinished work elsewhere; explicit Refresh
permits one retry per failed folder per run. Failed paths are excluded from native
index watches so they cannot repeatedly schedule work. The live file list retains
its independent watcher. Notifications after a partial attempt repair their affected
branches without restarting a full-tree scan. Cancellation retains resume behavior.
The processed counter includes discovery and verification metadata operations, so
it can exceed the saved-entry count. An unchanged resume verifies metadata once.
After completion there is no periodic full-tree validation.

An incomplete view exposes **Index details…** beside the bottom status controls
(including the shared workspace and detached-window controls). This on-demand,
read-only worker query lists scan errors with their original messages, unfinished
enumeration checkpoints, and folders needing recheck. Counts cover the entire
current subtree; the dialog shows at most 500 rows, with scan errors first.
Paths appear only in this explicitly opened dialog. Diagnostics never start a scan
or wait for the index writer. Verification errors preserve the failed file path.
 The first visit to a folder per app session checks its immediate
entries; later visits read saved sizes without acquiring the index writer. The
file list still reads live contents independently. Checks are shared by browsers
using the same cache instance; notifications and explicit Refresh bypass reuse.
Current-folder filesystem notifications and browser copy/move/rename
operations check affected folders. New or changed branches are scanned, removed
branches are purged, and recursive saved totals propagate to indexed ancestors.
Changes missed in an unwatched folder can remain cached after its first session
check until the user presses **Refresh**, which validates the entire current subtree.

`DirectoryCache.reconcile_folder()` updates completed generations in one writer
transaction without copying the whole generation. Independent SQLite read snapshots
retain their old contents. Cancellation rolls back updates to a completed index, retaining the previous
saved contents; initial/partial scans retain their durable checkpoint/resume behavior.
Explicit Refresh validates the subtree in bounded batches in the same generation,
so saved totals also update in its indexed ancestors. Retired metadata cleanup only
examines records touched by the update, keeping repeated edits from growing the cache. The
additive `folder_checks` table records the last immediate-folder check separately
from full-tree validation timestamps, without rebuilding the index. The status line
shows last-checked time and distinguishes cached subtree sizes from full validation.

The browser has no visible Pause/Resume scan control. Initial scans finish once;
explicit Refresh and filesystem changes drive subsequent work. The old pause
methods and hidden compatibility object remain available to existing callers.

During initial/resumed discovery, open views register lightweight in-memory folder
priorities. The scanner checks needed ancestors and those folders' immediate entries
before ordinary pending work, consulting new requests between folders. Priorities
stop at the visible folder, so the rest of the original scan still completes. Visible
sizes are published promptly. Navigating inside an active scan keeps the same job,
generation and root; worker snapshots follow each subscriber's visible folder. Other
tabs can have different visible folders in the same shared scan. Closing removes
that view's priority; pausing retains independent subscription cancellation.

The idle **Refresh index** action sits at the bottom-right beside status/activity.
Docked tabs use one workspace control for the active folder. Detached tabs restore
their own local status/activity and refresh control; docking again hides that local
row. Refresh controls hide during indexing. Radial centre double-click goes up one
folder using the normal Up action, preserving the selected chart mode and browsing
root boundary.

Disjoint initial-scan roots retain independent jobs and serialize their writers;
closing a waiting window does not interrupt another window's scan. Priority moves
folders within an ongoing scan's tree; it does not add unrelated roots to that tree.
Integration coverage uses real Logistics browser views in two workspaces, tabs and
floating docks, checking early sizes, shared generations, close/cancel isolation,
priority cleanup, active-folder Refresh and detach/reattach status visibility.

## Compact cache (schema 3)

`folder_paths` stores a folder's cached absolute address, parent ID, segment name,
and natural-sort prefix. `entry_nodes` stores a filename, parent folder ID, folded
name and filename-only sort key. `entry_records` stores immutable metadata versions.
`generation_entries` stores integer references. Overlapping roots and scan rebuilds
share unchanged names/metadata; changing a file creates a new metadata version.
Folder checkpoints, errors and aggregate totals remain generation-specific, with
their established path-based representation. Returned `Entry.path` values are still
absolute paths; callers do not need to understand database IDs.

Whole-filesystem scans on macOS omit `/System/Volumes/Data`: macOS firmlinks
already expose its files through `/Users`, `/Applications` and other ordinary
paths. Scanning both would count the same files twice. Explicitly indexing Data
or one of its subfolders remains supported; other volumes remain included.
The next index update removes this branch from existing whole-filesystem
generations and recalculates ancestor totals without requiring a full rescan.
Repair runs under the index writer lock and rolls back on cancellation; old
display snapshots remain readable. Read-only saved-size loading does not perform
the repair. Sizes represent logical file bytes, so hard links, APFS clones and
sparse files can still make totals differ from physical disk usage.

Scoped reads/copies/deletes use indexed folder IDs. Filesystem identities and
metadata still need validation; compact storage does not turn filesystem enumeration
into a journal-based index. Natural path order is preserved by combining each cached
folder prefix with its filename key during reads. Broad result sorting can use a
SQLite temporary sort; immediate-child charts do not traverse the whole generation.
Folder reconciliation uses the covering `folder_parent(generation,parent,path)`
index. Without it, every folder scan examines all saved folder checkpoints. Existing
schema 3 databases receive this index on the next writer initialization; no metadata
rebuild is needed. Only one copy of the pending-folder queue index is retained.

Upgrades run under the writer lock. Before upgrading an existing schema 1/2 cache,
a SQLite backup creates `directory-index.pre-v3.sqlite3` beside the index, including
committed WAL data. It is retained and never overwritten. Failure/cancellation
rolls back the migration, and read-only legacy snapshots remain displayable before
and during upgrade. Completed generations and partial checkpoints are preserved.
Deleted generations prune only their unreferenced metadata/names; other scopes and
existing readers retain their versions.

Dropping old tables frees pages for SQLite to reuse, but does not necessarily shrink
the main file's allocated size immediately. We do not automatically run `VACUUM` on
large live caches: it adds a full rewrite and can retain extra WAL data while readers
are active. The recovery copy is also intentionally separate from the new cache.

## Validation

Use isolated temporary databases; never point test browsers at the live user cache.
Run Qt suites with `QT_QPA_PLATFORM=offscreen`, in separate processes when testing
many modules. Coverage includes migration/WAL/rollback/cancellation, old snapshots,
overlapping roots, partial resume, changed metadata, literal/Unicode names, natural
ordering, scope query plans, indexing subscriptions, preview sizing, file actions,
and Logistics comic/extension integration.

Profile filesystem metadata, database writes/checkpoints, aggregation and validation
separately. Record warm/local versus cold/network conditions and fixture sizes.
Measure SQLite used pages (page count minus freelist) separately from allocated file
size. For large migration rehearsals, copy committed data into a temporary database
and verify entry counts plus SQLite integrity/foreign-key checks afterward.

### Radial navigation and breadcrumbs

Opening a radial folder or returning to its parent uses a 240 ms zoom transition.
Ordinary index updates do not restart it. Hit testing uses the painted geometry,
and double-click navigation stays available during the transition. Hidden charts
stop their animation timer. Set `[Storage] radial_animations_bool = false` in
`ui/settings.ini` to disable transitions.

Breadcrumb separators are painted chevrons centered geometrically, avoiding
platform-specific font baselines. The bar has a subtle palette-aware backdrop.

### Disconnected drives: current limits

`DirectoryCache.peek()` can read saved data without accessing the drive. However,
scanning a parent can prune missing child folders, and the index does not yet track
volume identities. Treat robust offline retention as pending work. A single database
with volume IDs, availability and last-seen metadata can distinguish unplugging
from deletion and avoid mixing different drives mounted at the same path. Automatic
age-based removal is not currently enabled; prefer explicit clearing until volume
tracking is implemented.

Cancellation of the last shared index subscriber connects its finish callback
before interrupting the worker and also checks already-finished workers. This
closes the race where a thread exits before the new callback is connected but
its GUI completion is still queued; handles always leave the busy state.

File-view keyboard navigation follows the host platform: macOS Command-Up goes
up, Command-Down/Command-O opens the selection, and Return renames. Windows and
Linux use Enter to open, F2 to rename, and Alt-Up to go up. Windows also accepts
Backspace to go up. Alt-Left/Right traverse history. Text fields and inline
filename editors retain their own keyboard handling.

Radial rendering caches one device-resolution scene until chart data, dimensions,
font or palette change. Selection and navigation zoom reuse it. Hit testing uses
ring distance and a binary search of angular sectors rather than checking each
curved path. The pointer-following tooltip is a reusable `ui.cursor_tooltip`
component, and hides during loading or when the pointer leaves. Chart data remains
bounded to four levels and 3,000 displayed entries, independent of index size.

### Snapshot ownership on Windows

Indexed snapshots retain a SQLite read transaction so displayed results stay
stable while another scan publishes a generation. Release a snapshot with
`snapshot.close()` when its owner is done, or use it as a context manager.
`DirectoryCache.close()` releases the snapshots owned by that cache; a cache can
also be used as a context manager. Close readers before removing a temporary
cache directory, especially on Windows where open SQLite files cannot be removed.
Do not close a shared cache while other views still use its snapshots. Browser
workers and tests must finish before their owning temporary resources are removed.


## Reusable file browser

**Start here for new extensions:** [Adding a feature](../../FEATURES.md) documents the
unified `register() -> Feature(...)` API, including complete action/type wiring,
handler context, per-window controllers and enable/disable behavior. The APIs below
also describe the lower-level hooks retained for existing integrations.

`commonUtils.ui.file_browser.FileBrowser` is an embeddable PySide widget for
folder/file browsing, selection, list/tile/column views, Back/Forward/Up navigation,
a clickable folder breadcrumb bar, information tabs, thumbnails and context menus. It uses
`File`/`Directory` objects resolved by the shared process-wide file registry.
`QFileSystemModel` supplies filesystem watching and Qt indexes; its browser adapter
exposes `item(index)` and `object_for_path(path)` as the data-object interface.

```python
from pathlib import Path
from commonUtils.dirUtils import Directory
from commonUtils.ui.file_browser import FileBrowser

browser = FileBrowser(Directory(Path('/path/to/library')), parent=window)
layout.addWidget(browser)
```

List, Tiles and Columns are selected using exclusive palette-aware icon buttons.
Tile cells divide the viewport width evenly, adjusting cover size before adding
columns. Resize, navigation and filesystem updates lay out items immediately.
Folder-only directories use compact square cells; in mixed directories, folder
icons occupy half the cover width by default. The tile-only **Size** menu adjusts
folder icons from 25% to 100%; this preference stays with the browser widget.
Tiles reserve a scrollbar gutter so scrolling cannot change the column count.
Column view uses small chevrons, stops at files and leaves unused space in the
current palette's window color. Preview content belongs to the adjacent panels,
without an extra empty file column.

Create a QApplication before the widget. Project-specific controls, such as a
library dropdown, belong outside this widget. `set_directory(Directory_or_Path)`
sets its navigation boundary; `navigate(path)` moves within that root. The path
bar starts with that root and includes only descendant folders, never selected
files. Each folder is clickable. Compact native arrow buttons provide Back,
Forward and Up, with tooltips and accessible names; existing navigation shortcuts
remain available. The root stays pinned at the left; longer paths
scroll their descendants while Back, Forward and Up remain available. The right
panel remains visible and always provides **File Information** for a selected
file/folder: path, name, extension/size where applicable, modification time,
creation time when the filesystem exposes one, readability, and link targets.
Details use compact aligned label/value rows, muted labels, selectable plain-text
values and wrapping for long paths/descriptions. Information tabs scroll vertically.
Preview icons come from the same per-path system icon provider as the file listing;
folder previews use a compact icon area instead of reserving cover-image space.
Unix change time is not mislabeled as creation time. Folder totals/counts are
calculated asynchronously without reading file contents or following links.
Refresh recalculates them; totals and thumbnails remain in memory.

Specialized File subclasses contribute behavior through GUI-independent hooks:

```python
from commonUtils.fileUtils import File
from commonUtils.filesystem import BrowserPanel, BrowserDetails, BrowserAction
from commonUtils.fileTypes.registry import register_file_type

class ProjectFile(File):
    def browser_panels(self):
        return (BrowserPanel('project.details', 'Project Information', self.load_details),)

    def load_details(self):
        return BrowserDetails(fields=(('Title', 'Example'),))

    def browser_actions(self, context):
        return (BrowserAction('project.edit', 'Edit Project Data',
                              lambda ctx: ctx.invoke('project.edit', ctx.selection),
                              source='Project'),)

register_file_type(ProjectFile, 'project')
browser = FileBrowser(Path('/path/to/library'),
    services={'project.edit': edit_selected_project_files})
```

Context menus put built-in Open/Reveal actions first, then group contributed actions
under their `BrowserAction.source` feature name. Supply a user-facing name such as
`Comics` or `Project`; older descriptors without a source appear under `Extensions`.
Actions also expose the source through a tooltip and QAction property. Contributions
are collected from every selected object and each action provider, deduplicated by
key, and retain provider order within each feature group. Right-clicking an item
outside the selection uses only that item. Action callbacks receive the captured
selection; features decide which selected objects they support.

Applications can install reversible browser extensions with
`browser.install_extension(owner, services={...}, action_providers=(...), folder_fields=...)`.
`set_extension_enabled(owner, False)` removes that layer's handlers/providers/fields;
`True` restores it. `remove_extension(owner)` removes its registration permanently.
Layers preserve install order and restore underlying handlers after disabling a
later overlapping layer. The browser refreshes previews and totals after changes.
These APIs manage browser capabilities, not controller/worker lifetimes; the host
retains those objects until existing jobs and windows finish.

Register types during application startup, before the first listing/browser use.
This is a guideline, not enforced. The registration remains available throughout
that process to every subsequent resolver and `Directory.list_files()` call.
Existing File instances retain their class; the browser re-resolves cached objects
when the registry revision changes. Domain classes live in the consuming project.

Panel loaders return `BrowserDetails(fields, thumbnail, message, payload)` and run
on a worker thread; do not access widgets from them. Generic information stays
available even if a contributed panel fails. Every applicable contributed panel
appears alongside File Information as a tab; panels cannot be interactively hidden. Optional `payload` lets the application retain
its loaded domain document through the `details_loaded` signal.

Action callbacks and `browser_activate(context)` run on the GUI thread.
`BrowserContext.selection` contains File/Directory objects; `context.widget` is the
browser, and `context.invoke(name, *args)` calls an application-supplied service.
Return True from activation when the type handles double-clicks; False uses the
default application. Implement `browser_has_thumbnail = True` and
`browser_thumbnail(size) -> bytes` to provide tile images without a format-specific
branch in the browser. Thumbnail hooks run off the GUI thread and use a bounded
128-item cache. The size argument is a physical-pixel bounding box, including the
display scale; return enough pixels within that box for sharp high-DPI rendering.
The tile **Size** control applies to folder icons, application icons and thumbnails.
All render within the selected bounds, preserve their aspect ratio, and keep captions
aligned. Extra viewport space widens the cells without enlarging the icons.
Cached covers are regenerated when a larger icon size or higher display scale requires
more pixels. Selected-panel thumbnails likewise retain physical resolution. Constructors and detection rules should stay cheap and avoid
loading full metadata until requested.

Every browser enables Cut, Copy, Paste and inline Rename by default, with native
clipboard shortcuts and F2. A slow second click edits the selected filename;
the basename is selected without its extension. Paste appears on folders and empty
view backgrounds, targeting that folder; it is omitted for individual files.
Transfers run in the background, preserve links, and use numbered copy names for
collisions instead of overwriting. Cut entries leave the clipboard only after
successful moves. Cancellation stops between items.

Menus order opening, clipboard actions, Rename, contributed tools and OS-specific
Reveal. `BrowserAction(category='rename')` places a command beside Rename;
`order` (default 100) orders commands and their feature groups. Directory menus
include Open; file menus offer default-application opening. Double-clicking a folder
navigates into it.
An optional `action_providers=(provider,)` argument allows application-level actions
for Directory objects or mixed selections; providers receive `(item, context)` and
return BrowserAction descriptors. `folder_fields(directory, stats)` may contribute
additional count fields using `stats.extension_counts`, without hardcoding project
formats into shared folder scanning.

Useful integration methods/signals: `selected_objects()`, `context_menu_for(index)`,
`refresh()`, `refresh_item(path)`, `selection_changed(objects)`, `details_loaded(result)`
and `refreshed()`. Actions should call refresh_item after saving their data.
Panel preferences are local to the widget. Neither selections nor file metadata
are persisted by the shared browser.

Close owners safely: `stop()` cancels queued work and returns whether workers are
still finishing. If True, hide/defer owner destruction until the `idle` signal;
otherwise close normally. `shutdown()` waits for workers during application exit.
Do not delete a browser while a panel/thumbnail operation is running.


### File browser organization

| Module | Responsibility |
| --- | --- |
| `file_browser/__init__.py` | Browser integration, context actions, panel loading and worker lifecycle. |
| `file_browser/model.py` | Qt filesystem indexes resolved to registered File/Directory objects. |
| `file_browser/views.py` | Selection and location shared across views; thumbnail worker scheduling. |
| `file_browser/tiles.py` | Immediate grid layout, compact folder cells and folder-icon sizing. |
| `file_browser/columns.py` | Column trails, small chevrons and preview-column compatibility. |
| `file_browser/thumbnails.py` | Bounded thumbnail cache, invalidation and physical-pixel requirements. |
| `file_browser/controls.py` | View icons, folder-size menu and navigation buttons. |
| `file_browser/navigation.py` | Root-bounded breadcrumbs and Back/Forward history. |
| `file_browser/details.py` | Aligned, selectable information fields. |
| `ui/operations.py` | Generic background callbacks and completion signals, shared by browser and non-browser UI. |

Tile sizing uses logical pixels for layout and physical pixels for rendering.
The folder-size control changes system folder icons without shrinking covers in
mixed directories. Folder-only directories also use tighter cells and rows.
Constructing or changing a view never reads file contents; registered thumbnail
and panel hooks do that work in background operations.




## Indexed search in the browser

The search input above the breadcrumbs searches cached names for files and folders
throughout the current subtree, case-insensitively. Queries run in separate workers
and never start filesystem scans. Automatic indexing and size collection use the
same scanner/generation; searches show cached results immediately, poll committed
partial discoveries while indexing, and label incomplete or paused results.
Clear the field (or Escape) to restore normal views. Results retain normal selection,
preview, activation, context actions and clipboard behavior; Show in browser navigates
to a folder or selects a file in its parent. Paging is 500 rows and sorting is global.

Completed and partial ancestor indices can answer subtree searches immediately and
seed newly browsed subtrees without re-enumerating unchanged folders. A new higher
starting folder also merges saved child indexes, preferring more specific checkpoints
when scopes overlap. Discovery fills missing branches before validating reused data.
Absolute paths identify entries; different symlink spellings are separate scopes.
List size sorting compares raw file bytes and cached recursive folder totals; unknown
sizes stay last in either direction, and newly received totals update the order.
Logistics workspaces show one indexing line at the bottom of the window, with
path-free phase names, saved-entry and processed-operation counters, average
entries per second, and seconds/minutes/hours elapsed. The tooltip also omits paths.
Elapsed time keeps updating during long database operations. Processed operations
include discovery and validation; a file can be processed in both phases. Standalone browser widgets retain
a local bottom status line. Discovery counters are cumulative for the current run;
they do not reset for each folder. Concurrent UI requests
reuse a validation completed within 30 seconds; explicit invalidation bypasses this
window. A newly opened subtree can read a freshly validated ancestor directly,
without copying a generation or rechecking every descendant. Existing explicit DirectoryCache.get calls retain immediate validation.
The current location and up to 128 indexed immediate children are watched for changes,
with debounced reconciliation. A 60-second periodic check (up to five minutes for slow
scans) validates recursive metadata to catch missed events and unwatched descendants.
Watchers are a latency improvement, not the only consistency mechanism. Watch limits
are bounded; no watcher is allocated for every entry in a huge tree. Refresh forces
reconciliation. Disconnected paths retain cached records and show an unavailable
status. New navigation cancels/supersedes scans and queries; close cooperatively waits
for workers, and cancelled indexing retains durable checkpoints.

`ProcessUpdate.metrics` optionally carries structured counters through the existing
ProcessRunner progress signal; its older positional fields remain unchanged.
`ProcessProgressWindow` / `open_process(..., context=...)` can show operation source
and destination plus transfer fields, while keeping raw output behind a collapsible
Details and logs control. Missing counters remain unknown. The actual exit result
owns completion, retries/cancellation remain in ProcessRunner, and stopped operations
clear live speed/ETA/active-transfer display while preserving measured progress.




## Selection preview

The Preview button is enabled by default. Details appear only for a nonempty
selection; clearing selection restores the full browsing area. Opening the pane
allocates roughly 30% of the available splitter width with a 220 px minimum and
room for the browser. The splitter remains manually resizable. Switching Preview
off keeps it hidden for subsequent selections and avoids starting detail loaders.
Existing explicit `load`, `preview`, `selected_objects`, `selection_changed`, and
panel extension APIs remain available. `[FileBrowser] preview_enabled=false` in
the shared INI changes the default for newly created tabs; the button overrides it
for the current tab.

Transfer percentages are explicitly percentages of work discovered so far. At
100%, a running process reads **100% of known work · Still running**, with a
scanning/final-check explanation. Totals can grow and the percentage can decrease.
Only a successful process exit displays **Complete**, using a green progress bar;
stopped operations retain their measured progress with a distinct stopped state.


The schema-3 directory index interns filenames by parent folder ID and shares
immutable metadata across overlapping roots and generations. Existing absolute
`Entry.path` APIs and resumable checkpoints are preserved. A transactional upgrade
retains `directory-index.pre-v3.sqlite3` for recovery; freed database pages are reused
without an automatic full-file rewrite. See [file browser maintenance](README.md)
for module responsibilities, compatibility contracts, storage and test guidance.
