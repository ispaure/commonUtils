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

`filesystem.index.Snapshot.folder_stats()` exposes logical `size`, known allocated
`disk_size`, and `disk_unknown` counts. `Entry.disk_size` uses -1 for unknown allocation.
`storage_children(..., metric='size'|'disk_size')` selects the ranking measure while
retaining logical size as the API default. See [index contracts](../../filesystem/index/README.md).

`filesystem.snapshots` supplies revision-verified file hashes and bounded tree
content inventories. `filesystem.relocation.relocate_directory` supplies verified,
non-overwriting relocation with link rebasing. Persisted schemas, migration timing
and conflict policy belong to callers. See [filesystem](../../filesystem/README.md).

## Formats, settings and persistence

| Need | Entry point / contract |
| --- | --- |
| Text/CSV data | `TXTFile`, `CSVFile`; existing write semantics are not universally atomic |
| JSON data | `JSONFile.read_json/write_json`; atomic writes, non-finite numbers rejected |
| Raster metadata | `formats.image_headers.image_header` (PNG/JPEG/WebP), `gif_header` (GIF container); explicit byte bounds, no pixel decoding |
| Markdown image sizes | `formats.markdown.images.image_size`; shared Obsidian width/height hint parsing |
| Structured XML | `XMLFile`; [XML examples](../../formats/xmlType.md) cover namespaces and repeated elements |
| INI documents | `INIFile.read/get/set/save`; string values, formatting preservation, parse/I/O errors propagate |
| Typed INI fields | `configuration.ini_schema`; explicit opt-in suffix validation, separate from INI storage |
| Shared preferences | `configuration.settings.get_setting`; default's type determines conversion, bad/missing values fall back without rewriting |
| Migration completion | `configuration.migrations.MigrationLedger`; host-owned IDs/callbacks, explicit pending/done state outside resettable overrides |
| Preference changes | `configuration.monitor.SettingsMonitor`; explicit paths, weak subscriptions, publication notifications and external polling; Qt adapter under `ui.settings.monitor` |
| Raw atomic saves | `persistence.atomic_write_bytes/atomic_write_json`; caller supplies policy, directory and validation |
| Editable text snapshots | `persistence.text`; strict encoding, bounds, conflict checks and exact unchanged-byte preservation |
| Recovery / merge | `SessionStore` and `merge_text`/`MergeSession`; callers own schema, locking and apply/save policy |

See [formats](../../formats/README.md), [configuration](../../configuration/README.md)
and [persistence](../../persistence/README.md). Conflict checks are not locks;
coordinate concurrent writers. Do not equate an INI editor's type validation with
application domain validation.

`archives.rebuilding` supplies manifests and selected-member replacement across
open ZIP adapters. Hosts own format-specific metadata and publication policy.
See [archives](../../archives/README.md).

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

[Application update contracts](../../runtime/updates/README.md) cover exact GitHub
branch commits and published releases, protected Git/archive transactions,
rollback receipts and detached apply/restart. Hosts own update policy and UI.

`runtime.protected_keys` supplies explicitly namespaced Android/iOS 256-bit key
adapters. Consumers own credential records, backup exclusions and key namespaces.
See [runtime](../../runtime/README.md).

## UI entry points

- [FileBrowser](../../ui/file_browser/README.md): embedding, selection, extensions,
  metadata and cooperative stop. `open_search()` returns an embedded panel.
- [Feature declarations](../../ui/features/README.md): data-only definitions and
  lazy per-browser installation; detailed contracts in [extensions](extension-points.md).
- [MarkdownViewer / MarkdownWindow / open_markdown](../../ui/markdown/README.md):
  preview by default, explicit editing, boolean save/navigation outcomes, and
  optional `directory` wiki navigation.
- [CodeEdit and companions](../../ui/code_editor/README.md): editing mechanics,
  search, diff/merge and optional syntax; host owns documents and save policy.
- `ui.text_editor.open_text_file` opens the host text editor (or a shared standalone
  `TextFileWindow`) without Markdown history.
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
- [UI appearance](../../ui/appearance/README.md): canonical modules under `ui.appearance`, including shared desktop/native-WebView formatting vectors.

Provider-backed file work uses `runtime.resources.local.LocalFiles`, contracts and
capabilities in `runtime.resources.provider`, and complete operations in
`runtime.resources.mutations`. Use `persistence.publication.save_transaction` for
backend-specific staged saves and `persistence.text.TextSession` for in-memory
text baselines. See the [provider API guide](../../ui/resource-providers.md).


## Portable and native item browsing

`runtime.browsing` supplies BrowseEntry/BrowseTree snapshots and shared
`provider_entries` conversion. Qt consumers use EntryModel/BrowserViews; native
mobile consumers use `ui.native_browser.NativeBrowser` with Toga list/tile views,
visible thumbnail loading and generic/rich file details. Source work, credentials
and activation remain host-owned. See the [resource provider contract](../../ui/resource-providers.md#native-list-and-tile-presentation)
for callback, revision, bounded-cache and shutdown requirements.

`ui.native_browser.recycled.RecycledBrowser` adds continuous recycled lists and
viewport-limited tiles. `BrowserPresentation` supplies appearance hooks;
`ui.native.recycled_list.RecycledList` and `ListAppearance` expose the reusable
row component independently. See the [continuous browser guide](../../ui/native_browser/README.md#continuous-mobile-browsing)
and [list contract](../../ui/native/README.md#recycled-lists).

`formats.markdown.wiki.MarkdownWiki` supplies a GUI-free local documentation
catalog with folder landing pages, body-heading titles (after optional YAML frontmatter) and recursive text/name search.

## Optional native Toga components

`ui.native.adaptive.AdaptiveSidebar` supplies reusable allocated-width sidebar/detail
presentation; `SidebarPolicy` and `allocated_width` load no toolkit.

`ui.native.markdown.MarkdownWikiView` supplies adaptive, read-only documentation
browsing and inline search; `ui.native.markdown_preview` renders bounded inert
HTML, with optional host-supplied raster image bytes through `image_source`.
See the [native API guide](../../ui/native/README.md#host-supplied-markdown-images)
for callback and size contracts. Both are reusable without Logistics or Qt.

`ui.native.navigation_state` supplies toolkit-independent destination state.
`ui.native.navigation.NativeNavigationHost`, `ui.native.routes.Routes`, and
`ui.native.image_canvas.ImageCanvas` supply explicitly imported Toga/native
presentation. Consumers own destinations, document policy and resource lifetimes.
`host.chrome.set_page_swipes(active, navigation=None)` reserves Apple horizontal
gestures for a visible reader; see the [native component contract](../../ui/native/README.md).

| Need | Explicit native module / entry point |
| --- | --- |
| Cooperative dispatch context repair | `event_loop.bind_cooperative_loop(loop)`; no loop creation |
| Disposable pressure/configuration notifications | `memory.MemoryPressure`; host callbacks choose effects |
| System document selection / stream export | `documents.pick_document`, `export_stream`, `cancel_document_picker` |
| Scoped native document byte access | `runtime.resources.documents`; no retained permission/bookmark |
| Native action menus | `menus.NativeMenu`; host supplies guarded invocation/context/fallback |
| Optional native row/tint/layout mechanics | `presentation` |
| Literal Find/Replace | `editor_search.EditorSearch(editor, container)`; host notifies text changes |
| Native source input, line numbers and syntax colours | `code_input.CodeInput(loop=..., filename=...)`; call `dispose()` on retirement |

`formats.code_syntax` shares language choices and detection with desktop;
ordinary text, Markdown, JSON, YAML, TOML and INI filenames resolve directly,
without scanning the Pygments filename registry on each editor change.
`formats.code_spans` provides bounded UTF-16 colour spans and logical line starts
without Qt. The native input uses the host's Pygments installation.

See [native components](../../ui/native/README.md) for lifecycle, callbacks and
Android bridge packaging. `tools.mobile_ci.stage` includes their Python/Java
sources and records untracked local native sources as dirty.

## Password entry and visibility

Desktop consumers import `password_field` from `commonUtils.ui.pyside.passwords`
to add an idempotent trailing reveal action to a `QLineEdit`; shared
`LineEdit(..., pw_field=True)` uses it too. See the [Qt backend reference](../../ui/pyside/README.md#password-fields).
Mobile consumers import `PasswordInput` from `commonUtils.ui.native.password_input`.
It exposes the input value, enabled state, focus and confirmation handler plus an
accessible native eye button. See [native password entry](../../ui/native/README.md#password-entry).
Both start masked and hide again on clear. Hosts own credentials and workflows.

`ui.native.draw_ready.wait_for_draw` supplies bounded native draw acknowledgement;
see [draw lifecycle](../../ui/native/README.md#native-draw-acknowledgement).

`ui.native.keyboard` supplies window-scoped iOS and subtree-bound Android
[keyboard dismissal](../../ui/native/README.md#keyboard-dismissal).

`runtime.progress.CoalescedProgress` and `runtime.streams.progress` provide
[coalesced cumulative read progress](../../runtime/streams/README.md#measured-reads)
without toolkit imports or application-specific loading state.

`ui.native.text_size.TextSizeBinding` supplies callback-driven native pinch
[text sizing and WebView reflow](../../ui/native/README.md#pinch-text-sizing).

`ui.native.transitions` and `ui.native.sliders` supply reusable
[page motion and slider painting](../../ui/native/README.md#transitions-and-sliders).

`ui.native.appearance` provides callback-driven [surface painting and batching](../../ui/native/README.md#surface-appearance-primitives).
`ui.appearance.colors` contains toolkit-independent ARGB and contrast utilities.

Native icon rendering: `commonUtils.ui.native.icons.IconSpec`, `IconRenderer`,
`android_drawable`, `android_path`, `apple_symbols`, `apple_vector`.
Artwork and palette policy are explicit consumer inputs; drawing helpers import
platform bridges lazily.

Native forms: `commonUtils.ui.native.forms.wrap_text`, `fit_text`, `fit_section`,
`FittedLabel`, `disclosure`, `group_rows`, `collapsible`. Import requires Toga;
platform bridges remain lazy. Consumer callbacks own styling and layout notification.

Native bars: `commonUtils.ui.native.bars.apple_bar_group`, `apple_bar_separator`,
`apple_bar_title`, `centered_title_width`, `android_bar`. Platform bridges load
only when a native constructor is called. Returned native views are consumer-owned.

`commonUtils.runtime.signals.CoalescedSignal`: loop-local weak async broadcast;
`waiter(initial=True)` returns a coalescing async callback, `notify()` wakes all
live subscribers. No GUI imports, timers or retained application owners.

Native Markdown hosts can use
`ui.native.markdown_images.folder_image_source(provider, document)` for bounded,
revision-checked provider image reads, including animated GIFs. Feed its callback
to `markdown_preview` or a formatted editor using `embedded_image`. See the
[native image contract](../../ui/native/README.md#host-supplied-markdown-images).

## Resource and dialog owners

- [Resource runtime](../../runtime/resources/README.md): canonical provider,
  selection, mutation, archive, document and path-validation modules.
- [Qt resource windows](../../ui/resources/README.md): browser, picker, editor
  and cooperative operation ownership.
- `ui.native` remains an optional lazy package. Its `display_msg_box_ok` and
  `display_msg_box_ok_cancel` wrappers load `ui.native.dialogs` on invocation;
  `dialogs.py` owns desktop-native message boxes. Explicit Toga components remain
  in their own modules. Importing the package loads neither Qt nor Toga.

## Search ownership

Use [the search API map](../../search/README.md) for filename, provider, document and multi-file content queries. UI owners retain debounce, workers, highlighting and document navigation. The optional PCRE engine imports QtCore without QtWidgets.

## Perforce checkout and command outcomes

`integrations.wrappers.perforce.P4File` and `P4FileGroup` preserve the existing
file fields, status precedence, prompts, placeholders and add/sync/edit workflow.
Checkout returns `False` on command failure or incomplete final readiness.
`P4File.run_p4_move()` and `P4FileGroup.force_get_latest()` now return boolean
command outcomes; neither refreshes model fields. Single-file post hooks run only
following successful command exits. Host save/export policy remains caller-owned.

`integrations.wrappers.perforce.p4_utils.exec_p4_arguments()` accepts an argument
sequence and returns `CommandResult` without a shell. The legacy string API
remains available. See [Perforce contracts and examples](../../integrations/wrappers/perforce/developer-guide.md).
