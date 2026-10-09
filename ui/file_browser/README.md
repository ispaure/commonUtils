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

The index backend is separated into `commonUtils._directory_reader` (immutable
SQLite readers), `_directory_schema` (migration, record interning and membership),
`_directory_store` (scan scheduling/checkpoints), `_directory_reconcile` (targeted
completed-index updates), `_directory_totals` (incremental
aggregation), and `_directory_order` (natural ordering). The old reader/order
imports remain available from `_directory_store`. Public access continues through
`commonUtils.directory_index`.

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

Navigation has its own toolbar row so left/right panes remain usable in smaller
windows. The inline **Size** slider immediately precedes View and adjusts tiles,
list icons and column icons. The workspace footer is outside the bordered view
panes; cached-only reads do not show scan activity.

Workspace tab dragging uses explicit left/right drop zones and a center tab-group
zone (`commonUtils.ui.workspace_drag`). Closing a worker-only browser tab removes
it from the visible layout immediately; the workspace retains its hidden dock in
`_retiring` until its owners report idle. A feature close refusal keeps the tab
visible. Whole-window shutdown checks both visible and retired owners.

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
typing. SQL and detached snapshots share these rules in `_directory_search.py`.
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
