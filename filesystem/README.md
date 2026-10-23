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
| Planned copy/move operations | `filesystem.transfers` |
| Snapshot removal plans and execution | `filesystem.removal` |
| Network-location detection | `filesystem.network` |

`commonUtils.filesystem` exports FilesystemObject, BrowserDetails, BrowserPanel,
BrowserAction, FolderStats, scan_folders, format_size and format_datetime. These
information/provider records do not require Qt widgets. File classes can supply
read-only details and encoded thumbnails; see [metadata extension contracts](../docs/developer/extension-points.md#supply-metadata-and-thumbnails).

`scan_folders()` is an aggregate API backed by the shared persistent index,
not an independent traversal. `visible_only=True` limits returned folder totals to
the root and immediate child folders; their sizes include known descendants.
Cancellation returns None. Inspect partial/stale metadata rather than assuming
saved sizes describe the current disk exactly.

Storage workspaces are disposable, but replacement staging must remain beside the
destination for atomic publication. Use [persistence](../persistence/README.md) for
publication; a temporary directory alone does not provide transaction semantics.

See [integration contracts](../docs/developer/contracts.md) for namespace and data ownership.

[Library overview](../README.md)

`local_access` lets a host reserve physical roots for virtual providers. Shared
ordinary file operations reject raw access to registered roots, including aliases
and recursive ancestor operations. See the [provider contract](../ui/resource-providers.md)
for registration, internal record grants and the scope of this safeguard.

## Verified content snapshots

`snapshots.file_revision(path)` returns device/inode/size/mtime-ns/ctime-ns.
`verified_file_snapshot(path, cancelled=...)` returns that revision and SHA-256
bytes, checking both descriptor and pathname before/after hashing. Callers choose
link policy. `tree_content_state(root, cancelled=..., max_entries=10000)` rejects
links/junctions, special files and hard-linked files and returns relative names
with SHA-256 hex (None for directories). Each file is verified independently;
the tree inventory is not a writer lock or atomic whole-tree snapshot.

## Directory relocation

`relocation.relocate_directory(source, destination)` never merges/replaces an
existing destination. It attempts an exclusive rename, otherwise stages a verified
copy and removes the unchanged source only after publication. Relative external
links retain their targets; internal links rebase onto the relocated tree.
Hard-linked/special files are rejected during copy verification. A linked root is
relocated as a link. Cleanup after publication may fail with both copies retained;
callers own recovery and migration decisions.

File snapshots compare pathname and descriptor identity/size/mtime across APIs,
then compare each full revision before/after reading. Windows can report creation
time through pathname `stat` and change time through `fstat`; their ctime fields
are not compared to one another. Both still participate in their own stability checks.

## Transfer implementation boundary

`transfers` and `relocation` share rename fallback, source revalidation and
post-publication cleanup mechanics from
[persistence transfers](../persistence/README.md#verified-transfer-phases).
Their plans and link/collision policies remain distinct; virtual provider moves
also retain their own capability and encoding checks. Read `MutationIncomplete`
publication/source state before deciding whether a retry is safe.

## Local operations and resource adapters

This package owns physical local paths, snapshots and the persistent metadata index. `runtime.resources` owns provider identifiers, capabilities and lifetimes for local/archive/platform storage. Providers adapt local operations and revalidate access; an index hit never grants file access. Shared transfer phases and publication live in `persistence.transfers` and `persistence.publication`, so the two interfaces do not need duplicate transaction engines. Reusable queries live in [search](../search/README.md); UI owns workers and presentation.
