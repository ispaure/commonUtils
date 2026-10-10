# filesystem

Generic filesystem information and browser contribution hooks without Qt.

Import from `commonUtils.filesystem`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `BrowserDetails`, `BrowserPanel`, `BrowserAction`, `FilesystemObject`, `FolderStats`, `scan_folders`, `format_size`, `format_datetime`

[Library overview](../README.md).

`transfers.py` owns the historical `file_operations` implementation; the centralized compatibility
adapter preserves existing consumers.

`removal.py` owns the historical `file_removal` implementation; the centralized compatibility
adapter preserves existing consumers.

`traversal.py` owns the historical `traversal` implementation; the centralized compatibility
adapter preserves existing consumers.

`network.py` owns the historical `network_filesystems` implementation; the centralized compatibility
adapter preserves existing consumers.

## API behavior

| Entry point | Purpose |
| --- | --- |
| `FilesystemObject` | Common read-only information and optional browser behavior for files/folders. |
| `scan_folders` | Compatibility API: recursive totals from the shared persistent index. |
| `format_datetime` | Human-readable local date/time, independent of platform strftime flags. |

## Related modules

- `files`: file objects and helpers.
- `directories`: directory objects and browsing helpers.
- `links`: symbolic links and shortcuts.
- `rename`: filename transformations and batch rename policy.
- `index`: persistent directory metadata, search and reconciliation.
- `storage`: capacity and storage accounting.

Example: `from commonUtils.filesystem.directories import Directory`.
