# Architecture and ownership

## Responsibilities and dependency direction

| Subsystem | Owns | Leaves to its caller |
| --- | --- | --- |
| Filesystem and formats | Paths, file snapshots, type resolution, traversal, metadata and index data | Domain file subclasses, overwrite/selection policy |
| Archives | Archive models, reading, validation, extraction and publication | Password prompts, workflow, software selection |
| Runtime and integrations | Cancellation, progress, diagnostics, streams, processes and OS adapters | Scheduling, error presentation, external tool installation |
| Configuration and persistence | INI/schema parsing, atomic writes, text snapshots and recovery storage | Domain validation, save timing, schemas and writer coordination |
| UI | Qt presentation, browser bindings, reusable editors and workspace lifecycle | Feature discovery, application navigation and document policy |

The intended flow is application policy → reusable UI/operations → data and runtime
mechanisms. Core registry declarations do not require Qt; filesystem information
hooks return data and image bytes rather than widgets. UI modules consume this
data and schedule work. There are legacy exceptions: diagnostics imports the UI
facade, and some file activation hooks lazily open a UI. Do not mistake the intended
boundary for a completely GUI-free transitive dependency graph.

commonUtils does not own Logistics' feature registry, Obsidian vault workflows,
comic/book application features or full text-editor workspace. Its Markdown reader
owns local document presentation, supported wiki links, callouts and properties.
Its code editor owns editing mechanics, while hosts own files/tabs/sessions.

## From a path to a browser action

1. The application registers format rules and optional subclass overrides.
2. `file_from_path()` resolves through the shared registry and constructs a file
   snapshot; Directory listings use the same resolver.
3. A browser obtains filesystem information and optional panel/thumbnail providers.
   Expensive providers run on workers; results return to the GUI owner.
4. A feature binding filters a captured selection by accepted types and invokes its
   action on the GUI thread. The handler starts a job if needed.
5. After mutation the application refreshes affected items/index information. Old
   File instances retain their original path and cached fields.

The registry is process-wide within the importing package namespace. Feature
bindings/controllers are per browser; selection and navigation are per view.
Feature dependency metadata is interpreted by the host, not an automatic plugin
loader in commonUtils. See [extension points](extension-points.md).

## Live browsing versus indexed metadata

The live filesystem model supplies browsing. SQLite snapshots supply recursive
search and folder sizes. These can disagree temporarily: an index may be partial,
old or awaiting a notification/explicit refresh. Search does not index file text.

Browsers can share a scan for the same database/location, while each subscription
retains its own visible folder and cancellation. Writers serialize across processes.
Old read transactions remain consistent while later generations or reconciliations
are published; release snapshots when their owner is done to avoid retaining WAL
storage. Network browsing disables automatic indexing and rich metadata work.
Hosts may opt into the durable process-shared coordinator: one OS-elected runner
handles queued requests, other processes follow progress and take over after exit.
The host retains/stops its runner independently of browser widgets; see
[index lifecycle](../../filesystem/index/README.md).

## Initialization and shutdown

Create one QApplication, validate optional dependencies, register types, construct
widgets, install bindings, and retain declarations/controllers. The host decides
when and how often to run `Feature.initialize`, and enforces dependencies.

Keep all widget access on the GUI thread. Cancellation is cooperative and may wait
for a filesystem call to return. Request it during close, retain the owner, and
retry only after the appropriate idle/completion notification.

| Interface | Meaning of return/completion |
| --- | --- |
| `FileBrowser.stop()` | **True means still busy**; defer close and retry on `idle` |
| `binding.prepare_close()` / controller `prepare_close()` | **False means not ready**; keep owner and retry on `idle` |
| `SearchPanel.prepare_close()` | False until its worker is retired; wait for `idle` |
| Editor `can_close()` | False vetoes close, including cancelled or failed saves |
| `OperationProgress.completed(result, error)` | Delivered after worker shutdown; inspect both error and operation result |

A widget's destruction is not a cancellation mechanism. Disabling/removing a
feature does not stop existing controller jobs. Workspace tabs may disappear while
workers retire, but the workspace retains hidden owners; whole-window shutdown
must include them. See [workspaces](../../ui/workspaces.md) and
[operation progress](../../ui/operation_progress.md).

## Persistence and failure boundaries

Atomic publication protects one destination; it is not a cross-process lock or a
multi-file transaction. Text/INI/Markdown layers add conflict and encoding rules.
Batch cancellation normally finishes the current item and records the remainder;
archive extraction stages individual members rather than promising all-or-nothing
extraction. UI progress reaching its end does not prove every item succeeded.

New result-based APIs expose explicit errors/outcomes. Legacy diagnostics may raise
`DebugException` and display dialogs; worker owners use `noninteractive_logging`
and present errors after returning to the GUI thread. Do not silently swallow
failure or generalize one operation's policy to every helper.

[Developer hub](README.md)
