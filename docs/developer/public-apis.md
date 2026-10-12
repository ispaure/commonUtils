# Choosing public APIs

The interfaces below have examples, exports, tests or consumer use supporting
external integration. This is a curated map, not a promise that every public-looking
name is stable. Concrete UI fields and consumer patch targets can still be
part of the integration contract; see [integration contracts](contracts.md).

## Files, types and directories

Use `commonUtils.filesystem.files.File` for a plain file snapshot, and
`commonUtils.formats.registry.file_from_path(path)` for specialization. Built-in
text, CSV, JSON, XML, INI, Markdown and archive classes resolve lazily; unknown
suffixes fall back to File. Direct `File(path)` never consults the registry.
Constructors do not prove content validity. File size can be `None` for a missing
file; other filesystem errors may propagate.

`File.copy_file`, `rename_file` and `move_file` return a **new plain File**. The old
object is not retargeted. Copy overwrites; rename preserves a destination unless
`force=True`; move supports staged cross-volume replacement. I/O errors propagate.
The same-named module functions have been removed; catch `OSError` in callers
that need boolean failure outcomes. Resolve the returned path again when a
specialized class is needed. See [files](../../filesystem/files/README.md).

`Directory(Path(...)).list_files(recursive=True, filter_extension=None)` returns a
list of registered objects, follows directory links and reports recursive loops
through critical diagnostics. Filters accept dotted or bare suffixes without case
sensitivity. Traversal is synchronous. Deleting a linked Directory removes the
link; `delete_contents()` refuses a linked root unless `follow_root_link=True`.
See [directories](../../filesystem/directories/README.md).

`filesystem.traversal.scan_directory` instead returns naturally sorted Paths,
supports masks/regex and cooperative cancellation, and skips nested directory-link
traversal. It raises filesystem errors, invalid-regex errors and
`OperationCancelled`. `max_depth=0` means unlimited depth when recursive scanning
is enabled. [Filesystem operations](../../filesystem/README.md) also cover removal,
transfers and rename plans.

## Formats, settings and persistence

| Need | Entry point / contract |
| --- | --- |
| Text/CSV data | `TXTFile`, `CSVFile`; existing write semantics are not universally atomic |
| JSON data | `JSONFile.read_json/write_json`; atomic writes, non-finite numbers rejected |
| Structured XML | `XMLFile`; [XML examples](../../formats/xmlType.md) cover namespaces and repeated elements |
| INI documents | `INIFile.read/get/set/save`; string values, formatting preservation, parse/I/O errors propagate |
| Typed INI fields | `configuration.ini_schema`; explicit opt-in suffix validation, separate from INI storage |
| Shared preferences | `configuration.settings.get_setting`; default's type determines conversion, bad/missing values fall back without rewriting |
| Raw atomic saves | `persistence.atomic_write_bytes/atomic_write_json`; caller supplies policy, directory and validation |
| Editable text snapshots | `persistence.text`; strict encoding, bounds, conflict checks and exact unchanged-byte preservation |
| Recovery / merge | `SessionStore` and `merge_text`/`MergeSession`; callers own schema, locking and apply/save policy |

See [formats](../../formats/README.md), [configuration](../../configuration/README.md)
and [persistence](../../persistence/README.md). Conflict checks are not locks;
coordinate concurrent writers. Do not equate an INI editor's type validation with
application domain validation.

## Index data

Import `DirectoryCache`, `directory_cache`, `Entry` and `Snapshot` from
`commonUtils.filesystem.index`. For tests or independent applications pass
`DirectoryCache(database=path)`. `get()` may scan, resume and validate;
`peek()` reads saved data and can return None. Neither belongs on the GUI thread.
`invalidate()` requests future work rather than scanning immediately.

`Snapshot.search_page(query, offset=0, limit=500)` returns `(entries, total_matches)`;
sorting applies before paging. `folder_stats()` returns path-keyed totals. Inspect
`complete`, `errors` and validation metadata before treating totals as current.
Close snapshots or use them as context managers. See the
[index guide](../../filesystem/index/README.md) for refresh/reconciliation differences.

Hosts that need shared background jobs across processes can opt into
`commonUtils.filesystem.index.coordinator.IndexCoordinator`. The host runs/stops
its worker and supplies any Qt notification bridge; cancelled subscriptions leave
durable requests available for takeover. See the coordinator contract in the
[index guide](../../filesystem/index/README.md#optional-process-shared-coordinator).

## Operations, processes and integrations

`run_command(arguments, timeout=..., idle_timeout=...)` waits and returns a
`CommandResult` with return code, stdout/stderr tuples and timeout/cancellation
flags. `success` requires exit code zero without timeout/cancellation. Launch errors
raise OSError. Use a sequence with the default shell-free mode; strings require
`shell=True`. Timeouts must be positive. Run it off the GUI thread.

`exec_cmd(time_out=...)` is a legacy shell-oriented interface whose timeout means
**idle output**, not maximum duration. New-terminal mode returns without capturing
completion. See [command wrapper](../../integrations/wrappers/cmdShellWrapper/README.md).
Desktop application launching, Steam and Perforce adapters retain their own platform
and external-tool requirements; consult [integrations](../../integrations/README.md).

`run_batch` returns completed, failed, remaining and cancelled outcomes. Failure
keys require hashable items; cancellation is checked between items. Streams check
between chunks and cannot interrupt an arbitrary blocking read. Downloads require
caller-supplied release/installed hashes and policy. [Runtime](../../runtime/README.md)
links these contracts and platform detection (`get_os`, `get_arch`, `OS`).

For GUI work use [OperationProgress](../../ui/operation_progress.md), which retains
worker ownership through completion. Critical diagnostics raise `DebugException`;
use `runtime.diagnostics.noninteractive_logging` around legacy operations in jobs
or headless flows where dialogs are inappropriate.

## UI entry points

- [FileBrowser](../../ui/file_browser/README.md): embedding, selection, extensions,
  metadata and cooperative stop. `open_search()` returns an embedded panel.
- [Feature declarations](../../ui/features/README.md): data-only definitions and
  lazy per-browser installation; detailed contracts in [extensions](extension-points.md).
- [MarkdownViewer / MarkdownWindow / open_markdown](../../ui/markdown/README.md):
  preview by default, explicit editing, boolean save/navigation outcomes.
- [CodeEdit and companions](../../ui/code_editor/README.md): editing mechanics,
  search, diff/merge and optional syntax; host owns documents and save policy.
- `ui.text_editor.TextFileEditor` and `ui.settings.ini_editor.INISettingsEditor`: embedding
  editors with `save`, `reload`, `is_modified`, `can_close` and `saved(path)`.
- [ArchiveContents](../../ui/archive_view/README.md): passive navigation and request
  signals; host performs preview/extraction/removal jobs and password handling.
- [Workspace and document hosting](../../ui/workspaces.md): transfer, split and
  close protocols; application policy remains explicit.

[Developer hub](README.md)

## Layered settings and shared styling

- [Layered INI APIs](../../configuration/README.md#software-defaults-and-sparse-personal-overrides): registration, validated reads, sparse saves and editor.
- [Styling](../../ui/styling.md): font roles, live bindings, accent/tint, application opt-in and host settings callback.

## Grouped UI modules

- [UI workspaces](../../ui/workspaces/README.md): canonical modules under `ui.workspaces`.
- [UI tasks](../../ui/tasks/README.md): canonical modules under `ui.tasks`.
- [UI readers](../../ui/readers/README.md): canonical modules under `ui.readers`.
- [UI settings](../../ui/settings/README.md): canonical modules under `ui.settings`.
- [UI appearance](../../ui/appearance/README.md): canonical modules under `ui.appearance`.
