# Directory index

Import `DirectoryCache`, `directory_cache`, `Entry`, `Snapshot`, `scan_metadata`
and `storage_totals` from `commonUtils.filesystem.index`. This subsystem owns metadata,
persistent search and sizes; [File Browser user workflows](../../ui/file_browser/user_docs/README.md)
belong with the UI.

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
paths, while explicitly indexing it remains supported. Sizes are logical file bytes,
not allocated disk usage; links, clones and sparse files need that distinction.

## Storage and concurrency

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

## Disconnected drives

`peek()` can read saved data without accessing the drive, but parent scans can
prune missing children. The index does not track volume identities; robust offline
retention and distinguishing drives mounted at the same path are not guaranteed.
Automatic age-based removal is not enabled. Use explicit clearing deliberately.

## Maintenance map

`metadata` owns public records and nonpersistent snapshots; `reader` streams immutable
SQL views; `store` and `scan` own scheduling/checkpoints; `reconcile` updates affected
folders; `schema` migrates records; `totals` derives aggregates; `search`, `order` and
`exclusions` centralize matching, stable ordering and scope policy. Public callers
should not depend on database IDs or mutate the schema directly.

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
