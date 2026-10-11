# Directory index

SQLite-backed directory snapshots, reconciliation, search and size totals. The reader and writer share schema definitions; UI consumers schedule workers rather than scan synchronously.

Import the public API from `commonUtils.filesystem.index`; the historical `directory_index` path shares this module identity.

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [__init__.py](__init__.py) | Persistent, resumable directory indexing shared by search and storage analysis. |
| [exclusions.py](exclusions.py) | Traversal exclusions shared by discovery and incremental reconciliation. |
| [metadata.py](metadata.py) | Reusable, cancellable directory metadata snapshots for discovery and analysis. |
| [order.py](order.py) | Stable natural path keys, shared by index migration and scanning. |
| [reader.py](reader.py) | Immutable, streamed directory-index readers with legacy-cache compatibility. |
| [reconcile.py](reconcile.py) | Atomic, folder-scoped updates for the browser's completed persistent index. |
| [scan.py](scan.py) | Scan-generation orchestration, discovery passes and publication. |
| [schema.py](schema.py) | Compact directory-index records and transactional upgrades. |
| [search.py](search.py) | Shared filename-query rules for SQLite snapshots and in-memory snapshots. |
| [store.py](store.py) | Directory scan scheduling, validation, and durable per-folder checkpoints. |
| [totals.py](totals.py) | Folder aggregates derived from the index, without another filesystem walk. |

[Parent guide](../../README.md)

## Index lifecycle and browser behavior

`commonUtils.filesystem.index` supplies immutable `Entry`/`Snapshot` metadata,
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

