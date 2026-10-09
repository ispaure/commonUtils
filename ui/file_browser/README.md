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
- `file_actions.py`, `editing.py`: file mutations and names; preserve source indices.
- `navigation.py`, `controls.py`: breadcrumbs, history and presentation controls.

The index backend is separated into `commonUtils._directory_reader` (immutable
SQLite readers), `_directory_schema` (migration, record interning and membership),
`_directory_store` (scan scheduling/checkpoints), `_directory_totals` (incremental
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

Preview is enabled by default, shown only with a selection, and starts at roughly
30% of the splitter width (minimum 220 px). Users may resize it or switch it off.
Disabled previews do not start selection detail loaders. Existing `preview_panel`,
`heading`, `message`, `cover`, `tabs`, `preview`, `load`, and selection signals remain
available. Explicit `load(item)` still displays requested details when Preview is
enabled, and `selected_object` remains available when automatic previews are off.
The INI setting `[FileBrowser] preview_enabled` supplies new-tab defaults.

The shared status line and tooltip contain phases/counters, never scanner paths or
tab titles. Processed counts include discovery and validation operations, not a
claim of unique files; rate is the average over the run. Elapsed time continues
updating while the worker is busy with SQL, and supports seconds, minutes and hours.

## Compact cache (schema 3)

`folder_paths` stores a folder's cached absolute address, parent ID, segment name,
and natural-sort prefix. `entry_nodes` stores a filename, parent folder ID, folded
name and filename-only sort key. `entry_records` stores immutable metadata versions.
`generation_entries` stores integer references. Overlapping roots and scan rebuilds
share unchanged names/metadata; changing a file creates a new metadata version.
Folder checkpoints, errors and aggregate totals remain generation-specific, with
their established path-based representation. Returned `Entry.path` values are still
absolute paths; callers do not need to understand database IDs.

Scoped reads/copies/deletes use indexed folder IDs. Filesystem identities and
metadata still need validation; compact storage does not turn filesystem enumeration
into a journal-based index. Natural path order is preserved by combining each cached
folder prefix with its filename key during reads. Broad result sorting can use a
SQLite temporary sort; immediate-child charts do not traverse the whole generation.

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
