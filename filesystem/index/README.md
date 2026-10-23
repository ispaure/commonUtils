# Directory index

Import `DirectoryCache`, `directory_cache`, `Entry`, `Snapshot`, `scan_metadata`
and `storage_totals` from `commonUtils.filesystem.index`. This subsystem owns metadata,
persistent search and sizes; [File Browser user workflows](../../ui/file_browser/user_docs/README.md)
belong with the UI.

The process-wide `directory_cache` is created on first access. Importing
`DirectoryCache` alone does not resolve desktop storage defaults; mobile hosts
must supply an explicit app-private `database` path.

## Read and own a snapshot

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from commonUtils.filesystem.index import DirectoryCache

with TemporaryDirectory() as temporary:
    root = Path(temporary) / 'documents'
    root.mkdir()
    (root / 'notes.txt').write_text('Example', encoding='utf-8')
    with DirectoryCache(database=Path(temporary) / 'index.sqlite3') as cache:
        with cache.get(root) as snapshot:
            entries, total = snapshot.search_page('notes', limit=50)
            print(total, [entry.path.name for entry in entries])
            print(snapshot.complete, snapshot.errors)
```

`get()` is synchronous and can scan, resume or validate; run it off the GUI thread.
`peek(root)` reads saved data and may return None. `get(refresh=True)` discards pending
work and rebuilds; `reconcile_folder(full=True)` validates a subtree in its current
completed generation. The browser's Refresh uses reconciliation, not a compulsory
rebuild. `invalidate(root)` cheaply requests future work; `clear(root)` removes
overlapping indices and is a separate writer operation.

Snapshots are immutable metadata views with a read-only entry sequence. Their
`complete`, `errors`, `scanned_at`, `validated_at` and `metadata_checked` fields
separate partial discovery and saved data from current validation. `search_page`
returns `(entries, total_matches)`, sorted before paging. Search is case-insensitive
filename matching, with all bare terms required and quoted separator-normalized
phrases; it is not content indexing or a wildcard language.

`folder_stats(paths=...)` limits aggregate reads to requested paths;
`children_of=...` requests a folder and its immediate children (mutually exclusive
with explicit paths). Their sizes still include known descendants. `scan_folders`
is an aggregate adapter; cancellation there returns None, while underlying
index APIs normally raise OperationCancelled.

Close snapshots when their owners finish, or use context managers as above.
SQLite read transactions keep old views consistent during replacement/reconciliation
and can retain WAL data. `DirectoryCache.close()` closes its readers; do not call it
while unrelated users of that cache still need snapshots. Windows particularly
requires closing readers before removing cache files.

## Discovery and reconciliation

Completed folders retain durable checkpoints. Cancellation preserves those and the
last complete index; an interrupted folder is enumerated again because an iterator
position cannot safely survive filesystem changes. Discovery prioritizes unvisited
branches and may publish partial sizes. Changing/unreadable folders are marked
partial rather than retried indefinitely. Explicit refresh retries failed branches.

Completed-index reconciliation changes affected folders and ancestors in a writer
transaction. Cancellation rolls that transaction back, unlike initial/partial scans
which retain checkpoints. Browser notifications repair affected branches; no periodic
full-tree validation runs after completion. First session visits can check immediate
entries, with subsequent visits reading saved sizes, subject to the host's index
policy. Missed unwatched changes remain cached until validation.

Nested links/junctions are listed without traversal; a linked root retains lexical
result paths. Network mounts and the index's own storage are excluded from scans.
Whole-filesystem macOS scans omit `/System/Volumes/Data` to avoid duplicating firmlink
paths, while explicitly indexing it remains supported. Logical size and allocated
size are cached separately. Links are excluded, and files are counted by path;
hard links and clones may therefore count shared storage more than once.
Scan exclusions are reduced to paths with no already-excluded ancestor before
enumeration. The cache directory covers its database/lock/sidecar files, and an
excluded mount covers nested mounts, avoiding redundant parent-path checks per entry.

## Storage and concurrency

### State ownership

`DirectoryCache` owns the database location, writer/session locks, invalidations,
visible-folder priorities and open reader snapshots. It composes a fresh
`DirectoryScan` controller for each `get()` call; it no longer inherits scan
orchestration. The controller names the ancestor-reuse, branch-seeding,
completed-generation reuse, work-generation preparation, discovery and final
publication phases.

Each writer operation gets a new [ScanState](operation.py), shared by its scan,
validation and aggregation helpers. This declares exclusions, blocked folders,
dirty totals, progress counters and checkpoint/aggregation timings in one place.
Scans, reconciliation and exclusion repair initialize it through the same writer
scope. `active_operation` is available for instrumentation while that scope is
active and is cleared even on cancellation or failure. `last_metrics` retains the
finished attempt's metrics. Internal instrumentation should read counters from
`active_operation`, rather than the former accidental cache attributes.

Only SQLite generations/checkpoints survive cancellation for resumption. No
transient operation object is reused by a later request. Reader transactions and
cache invalidations retain their existing independent lifetimes. Reconciliation
still rolls back changes on cancellation; initial scans retain durable progress.
The [operation-state tests](../../tests/test_index_operation_state.py) exercise
these lifetime boundaries with disposable databases and retained readers.

The default path is `directory_index_path()`:

- macOS: `~/Library/Application Support/commonUtils/Cache/directory-index.sqlite3`
- Windows: `%LOCALAPPDATA%/commonUtils/directory-index.sqlite3`
- Linux: `$XDG_CACHE_HOME/commonUtils/directory-index.sqlite3` (default `~/.cache`)

See [storage paths](../storage/README.md); custom caches use `DirectoryCache(database=...)`.
One database holds roots/scopes without a fixed entry/root count cap. File contents
are not stored. WAL/SHM files accompany open connections, and a writer lock serializes
processes. Lock waits and long queries support cooperative cancellation; blocking
filesystem calls must return before cancellation is observed.

Browser windows can share same-location work; each view retains its own subscription
and visible-folder priorities. Independent roots retain separate jobs. Releasing
one subscriber must not cancel another's scan. Index scheduling does not make widget
access safe from workers.

## Optional process-shared coordinator

`IndexCoordinator` in `filesystem.index.coordinator` supplies a durable browser-job
queue beside a `DirectoryCache` database (`.jobs.sqlite3`, plus `.jobs.lock`). A host
runs `coordinator.run(cancelled)` off the GUI thread in every participating process
and sets `cache.coordinator` while it is available. Logistics supplies this lifecycle.
Standalone `DirectoryCache` calls keep their synchronous semantics and writer lock.

`reconcile_folder()` submits or follows a job and returns a saved snapshot; `submit`,
`status`, `active_job` and `follow` also support explicit subscriptions. Cancelling a
follower only detaches it. Submitted jobs survive subscribers; a process with no
subscribers can take over, and the next host launch resumes work if all hosts exited.
An OS-held runner lock prevents competing runners; actual index writes additionally
retain the existing writer lock. Ownership never expires on a timer. Abrupt death
releases both OS locks; normal stop checkpoints cooperatively. In-progress receipts
are retried after takeover; terminal errors/partial attempts require a new request.

Compatible active requests coalesce. Recursive initial discovery/full refresh can
cover descendant requests; a completed parent's immediate-folder check cannot.
Refresh and change notifications arriving during a running job queue a later pass.
The runner rechecks coverage if another operation completed a queued root first.
Terminal receipts are retained for seven days and pruned on submission. Queue
transactions are short and independent of long index transactions. Progress is
polled on workers; saved snapshots remain readable throughout. Priority hints from
open views expire after 15 seconds, but their expiry never changes writer ownership.

Hosts may supply `notify(job)` and bridge it through a queued Qt signal exposed as
`cache.shared_activity` before constructing browsers. This lets idle/cache-only
views follow work started later elsewhere. Exclusions are computed on the worker.
A followed parent remains the source for that view's search/sizes even when an
older independent child index exists. Progress messages are sanitized by the UI;
receipt errors remain local diagnostic data. Hosts must stop/join their runner
before destroying it. No external daemon, network service or arbitrary operation
replay is involved.

An optional `set_priority(background)` callback applies the original submitter's
saved background-priority setting when a runner starts or resumes the job. Joining
an existing job does not change its priority. Shared queue contention has bounded,
cancellable retries; it never authorizes a second index writer.

## Disconnected drives

`peek()` can read saved data without accessing the drive, but parent scans can
prune missing children. The index does not track volume identities; robust offline
retention and distinguishing drives mounted at the same path are not guaranteed.
Automatic age-based removal is not enabled. Use explicit clearing deliberately.

## Maintenance map

`store.DirectoryCache` remains the public facade and schedules work; `scan`
traverses folders. Internal phases have explicit owners:

| Module | Responsibility |
| --- | --- |
| `writer.WriterSession` | Cancellable thread/process writer lease, legacy backup migration, WAL/schema setup and connection retirement |
| `generations` | Bounded durable checkpoints and completed-generation publication/retirement |
| `seeding` | Reuse of saved descendant branches with explicit exclusions |
| `snapshots` | Snapshot assembly and retained read ownership |
| `reader`, `metadata` | Immutable SQL views and public records |
| `reconcile`, `schema`, `totals` | Affected-folder updates, migrations and aggregates |
| `search`, `order`, `exclusions` | Matching, stable ordering and scope policy |

Writer phases run under the same owned lease; snapshot readers retain their own
consistent views and must close independently. Cancellation can leave resumable
folder checkpoints; incomplete work is not published as a completed replacement.
These internal splits do not change cache paths, schema or the public facade.
Callers must not depend on database IDs or mutate the schema directly.

## Compact cache (schema 4)

`folder_paths` stores a folder's cached absolute address, parent ID, segment name,
and natural-sort prefix. `entry_nodes` stores a filename, parent folder ID, folded
name and filename-only sort key. `entry_records` stores immutable metadata versions.
`generation_entries` stores integer references. Overlapping roots and scan rebuilds
share unchanged names/metadata; changing a file creates a new metadata version.
`entry_allocations` stores allocation per immutable record. File fingerprints include
allocation so allocation-only changes produce a new record, preserving old readers.
`Entry.disk_size` is allocated bytes or -1 when unavailable. `FolderStats.size`
remains logical bytes; `disk_size` sums known allocations and `disk_unknown` counts
files without allocation metadata. Folder totals persist both measures and the
unknown count; incremental reconciliation propagates them to changed ancestors.
`Snapshot.storage_children(..., metric='size')` retains logical-size compatibility;
`metric='disk_size'` sorts and returns known allocated bytes (unknowns have no area).
POSIX uses `st_blocks * 512`. Windows reads allocation through attribute-only handles,
or compressed/sparse storage metadata, without reading file contents.

Schema 3 upgrades retain all generations, checkpoints and logical totals. A
`.pre-v4.sqlite3` backup includes committed WAL data; the schema update is atomic.
Existing totals initially count their files as allocation unknown. Metadata validation
fills allocations without discarding saved logical sizes; read-only loading never
performs that scan. Schema 1/2 still use the existing `.pre-v3.sqlite3` recovery copy
before upgrading their compact records.

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
the repair. Both size measures count files by path, so hard links and APFS clones
can still make totals differ from exclusive physical disk usage.

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

## Maintainer validation

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


[Developer architecture](../../docs/developer/architecture.md) · [Filesystem overview](../README.md)

Coordinator receipt reads inspect an existing queue schema without requesting a
DDL write lock, so readers can follow work while another connection holds the
queue writer reservation. Initial schema creation retains normal SQL retries.

Metadata scanning and Windows index checks use the existing portable junction
query, including its reparse-tag fallback on Python versions before 3.12.
Directory links remain excluded from recursive payload totals.
