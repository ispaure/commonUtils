# Filesystem utilities

Choose an interface by whether you need file objects, plain paths, live operations
or saved metadata. These interfaces have different traversal and failure contracts;
see the [developer API guide](../docs/developer/public-apis.md#files-types-and-directories).

| Need | Start here |
| --- | --- |
| File information and copy/move/rename methods | [File objects](files/README.md) |
| Registered file objects from a directory | [Directory](directories/README.md) |
| Plain paths, masks and cancellable traversal | `filesystem.traversal.scan_directory`; skips nested directory links |
| Symlinks, junctions and platform shortcuts | [Links](links/README.md) |
| Batch filename changes | [Rename](rename/README.md) |
| Persistent filename search and recursive sizes | [Directory index](index/README.md) |
| Cache paths and private temporary workspaces | [Storage](storage/README.md) |
| Planned copy/move operations | `filesystem.transfers` (historical `file_operations`) |
| Snapshot removal plans and execution | `filesystem.removal` (historical `file_removal`) |
| Network-location detection | `filesystem.network` (historical `network_filesystems`) |

`commonUtils.filesystem` exports FilesystemObject, BrowserDetails, BrowserPanel,
BrowserAction, FolderStats, scan_folders, format_size and format_datetime. These
information/provider records do not require Qt widgets. File classes can supply
read-only details and encoded thumbnails; see [metadata extension contracts](../docs/developer/extension-points.md#supply-metadata-and-thumbnails).

`scan_folders()` is a compatibility API backed by the shared persistent index,
not an independent traversal. `visible_only=True` limits returned folder totals to
the root and immediate child folders; their sizes include known descendants.
Cancellation returns None. Inspect partial/stale metadata rather than assuming
saved sizes describe the current disk exactly.

Storage workspaces are disposable, but replacement staging must remain beside the
destination for atomic publication. Use [persistence](../persistence/README.md) for
publication; a temporary directory alone does not provide transaction semantics.

Historical aliases share canonical module identity through the centralized
[compatibility adapter](../docs/developer/compatibility.md).

[Library overview](../README.md)
