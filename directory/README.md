# Directory index

SQLite-backed directory snapshots, reconciliation, search and size totals. The reader and writer share schema definitions; UI consumers schedule workers rather than scan synchronously.

Import the public API from `commonUtils.directory`; the historical `directory_index` path shares this module identity.

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

[Parent guide](../README.md)
