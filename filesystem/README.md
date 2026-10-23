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

The same guard applies before legacy File copy/move/rename/deletion and permission
changes, and before Directory deletion/content deletion. Ancestor directory
operations preflight registered descendants before touching ordinary siblings;
denied renames do not create destination parents. Ordinary unregistered paths
keep their established behavior, and exact backend-record grants remain scoped.
This routes host-managed storage through its provider; it is not an OS sandbox
for arbitrary external filesystem calls.

An unresolvable looping leaf symlink is checked by its resolved parent and name,
so an unrelated provider does not prevent unlinking that ordinary link. Links
inside a protected root remain denied; resolvable aliases retain target checks.
The fallback does not resolve looping ancestors or grant access through a loop.

## Verified content snapshots

`snapshots.file_revision(path, follow_symlinks=True)` returns
device/inode/size/mtime-ns/ctime-ns. Pass `follow_symlinks=False` for the link
object’s own revision; the default continues to follow it.
`verified_file_snapshot(path, cancelled=...)` returns that revision and SHA-256
bytes, checking both descriptor and pathname before/after hashing. Callers choose
link policy. `tree_content_state(root, cancelled=..., max_entries=10000)` rejects
links/junctions, special files and hard-linked files and returns relative names
with SHA-256 hex (None for directories). Each file is verified independently;
the tree inventory is not a writer lock or atomic whole-tree snapshot.

`copy_content_state(root)` compares a staged file/tree using SHA-256 bytes,
object kinds and raw symbolic-link targets. Its mapping includes `.` for the
root and uses POSIX relative names with `('file', digest_bytes)`, `('directory',)`
or `('link', raw_target)` values. It deliberately permits ordinary hard-linked
files and does not rebase links; relocation and private tree inventories retain
their different policies. Special objects are rejected. Callers own source
revision checks, limits, staging and publication; this inventory is not a lock.

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

## Cross-volume move integrity

Clipboard `transfer_paths(..., move=True)` and `File.move_file` verify staged
content before cross-volume publication, then recheck source revisions immediately
before removal. Clipboard revisions include ctime as well as metadata identity.
A corrupt copy leaves the source and existing destination untouched; an observed
source edit after publication retains both copies and reports incomplete cleanup.
No-replace clipboard destinations and the low-level File method's existing
replacement policy remain distinct. Files, directories, empty folders and raw
symbolic links retain their established transfer meanings.

The verification requires a hash read of the source and staged copy; same-volume
renames and ordinary clipboard copies keep their prior path. Cancellation remains
between clipboard items. Source checks are not an external writer lock: another
process can still edit after the last check, so callers must coordinate writers
when strict exclusion is required.

Storage relocation also rechecks the source immediately before cleanup, including
root-link revisions. A late source edit or retargeted root link after publication
retains the source and new location and raises `MutationIncomplete` with
`destination_published=True`. Relative/internal link rebasing and no-overwrite
migration policy are unchanged; callers must resolve both-location conflicts
rather than blindly retrying a completed publication.

## Executable permissions

`File.set_executable_permission()` retains native `chmod +x` and its umask
semantics, passing an absolute filename as a literal argument with `shell=False`.
Quotes, substitutions and option-like relative filenames are never shell syntax.
Command failures raise OSError instead of silently continuing; the existing
15-second idle-output timeout remains. The host provider guard runs first.
