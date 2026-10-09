# UI Utilities

The `commonUtils.ui` package provides reusable cross-platform UI helpers with both **native** and **PySide6** backends.

Generic message boxes can be called directly through `commonUtils.ui`. When `use_pyside` is enabled, the package attempts to use PySide first and falls back to the native backend if PySide is unavailable or fails.

## Backends

### 📄 `__init__.py`

Provides the generic UI interface and lazy backend loading.

Currently available generic functions:

- `display_msg_box_ok()` — display an OK message box
- `display_msg_box_ok_cancel()` — display an OK/Cancel message box and return the user's choice

```python
from commonUtils import ui

ui.use_pyside = False  # This standalone example has no QApplication.
ui.display_msg_box_ok("Example", "Operation completed")

if ui.display_msg_box_ok_cancel("Example", "Continue?"):
    print("Continuing")
```

Set `ui.use_pyside` to control whether supported generic functions should attempt
to use PySide first. Its default is True. When PySide is installed, create a
QApplication before calling a generic dialog, or use the native backend as above.
Qt may abort the process if a widget is created without an application; Python
exception fallback does not make that safe.

The individual backends are also lazily available as:

```python
ui.native
ui.pyside
```

### 📄 `native.py`

Provides lightweight message boxes without requiring PySide or another Python GUI framework.

Platform-specific implementations use:

- **Windows** — native Windows message-box APIs
- **macOS** — AppleScript
- **Linux** — `kdialog`, `zenity`, or `xmessage`, with a console fallback

The native backend currently provides OK and OK/Cancel dialogs.

### 📁 `pyside/`

Provides the more complete PySide6 UI toolkit used for building application interfaces.

This backend requires the optional `PySide6` dependency and an existing
QApplication before creating any widget or showing a message box. The PySide
snippets below assume the application has performed the setup shown next.

```python
from commonUtils.ui import pyside

# Legacy commonUtils.pySideUtils imports resolve to this same module.
# Implementations are grouped into application, widgets, windows, messages and progress.
q_app = pyside.initialize_q_app()  # Once per process; retain this object.
```

Available helpers include:

- `Window` — base dialog or main-window abstraction
- `button()` — create a push button and connect it to a function
- `button_open_win()` — create a button that opens another window
- `Label` — label wrapper
- `LineEdit` — text-entry wrapper with optional password mode
- `create_checkbox()` — checkbox creation
- `create_frame()` — framed UI panel
- `create_grid()` — grid-layout creation
- `create_scroll_area()` — scrollable content area
- `create_scroll_area_grid()` — scrollable grid area
- `create_size()` — create scaled `QSize` values
- `set_font()` — apply the common UI font settings
- `Palette` — palette helpers, including dark and navy palettes
- `initialize_q_app()` — initialize the PySide `QApplication`

#### Message Boxes

The PySide backend provides several configurable message-box combinations:

- OK
- OK / Cancel
- Ignore / Abort
- Yes / No
- OK / Help

Message boxes support configurable icons, dimensions, and callback functions where applicable.

```python
from commonUtils.ui import pyside

pyside.display_msg_box_yes_no(
    "Confirmation",
    "Continue?"
)
```

#### Progress Bars

`ProgressBar` and `ProgressBarWindow` provide reusable progress UI.

A progress window can be created with:

```python
from commonUtils.ui import pyside

progress = pyside.display_progress_bar("Processing")
```

The progress-bar implementation supports updating progress and displaying status text while an operation is running.

## PySide Application Setup

Create one QApplication per process, as shown above. In an existing Qt application,
reuse its application rather than call `initialize_q_app()` again. The helper
configures Fusion style and applies platform-specific setup where required.
Standalone windows also need an event loop (`q_app.exec()`); see the complete
[browser example](../FEATURES.md#runnable-example-add-a-menu-action-to-a-browser).

## Dependency

Most of `commonUtils.ui` does not require PySide6 when the native backend is used. Install `PySide6` only when the PySide-specific functionality is needed.

```text
PySide6
```

Because the backends are lazily imported, accessing the native UI does not unnecessarily import PySide.


## Background work and downloads

Use [the workflow recipes](../RECIPES.md) for complete examples of
`OperationProgress`, safe dialog closing, per-item batch cancellation, stream
progress and verified download prompts. The synchronous legacy progress widgets
only display progress; callbacks must use an explicit worker to avoid blocking Qt.
The generic worker lives at `commonUtils.ui.operations.Operation`.

For automatic background work that should not change the layout, pass
`show_progress=False` to `OperationProgress.start()`. Completion, progress reporting
and `request_cancel()` still work; callers provide their own cancellation control.
The default continues to show the progress widget.

## Reusable file browser

**Start here for new extensions:** [Adding a feature](../FEATURES.md) documents the
unified `register() -> Feature(...)` API, including complete action/type wiring,
handler context, per-window controllers and enable/disable behavior. The APIs below
also describe the lower-level hooks retained for existing integrations.

`commonUtils.ui.file_browser.FileBrowser` is an embeddable PySide widget for
folder/file browsing, selection, list/tile/column views, Back/Forward/Up navigation,
a clickable folder breadcrumb bar, information tabs, thumbnails and context menus. It uses
`File`/`Directory` objects resolved by the shared process-wide file registry.
`QFileSystemModel` supplies filesystem watching and Qt indexes; its browser adapter
exposes `item(index)` and `object_for_path(path)` as the data-object interface.

```python
from pathlib import Path
from commonUtils.dirUtils import Directory
from commonUtils.ui.file_browser import FileBrowser

browser = FileBrowser(Directory(Path('/path/to/library')), parent=window)
layout.addWidget(browser)
```

List, Tiles and Columns are selected using exclusive palette-aware icon buttons.
Tile cells divide the viewport width evenly, adjusting cover size before adding
columns. Resize, navigation and filesystem updates lay out items immediately.
Folder-only directories use compact square cells; in mixed directories, folder
icons occupy half the cover width by default. The tile-only **Size** menu adjusts
folder icons from 25% to 100%; this preference stays with the browser widget.
Tiles reserve a scrollbar gutter so scrolling cannot change the column count.
Column view uses small chevrons, stops at files and leaves unused space in the
current palette's window color. Preview content belongs to the adjacent panels,
without an extra empty file column.

Create a QApplication before the widget. Project-specific controls, such as a
library dropdown, belong outside this widget. `set_directory(Directory_or_Path)`
sets its navigation boundary; `navigate(path)` moves within that root. The path
bar starts with that root and includes only descendant folders, never selected
files. Each folder is clickable. Compact native arrow buttons provide Back,
Forward and Up, with tooltips and accessible names; existing navigation shortcuts
remain available. The root stays pinned at the left; longer paths
scroll their descendants while Back, Forward and Up remain available. The right
panel remains visible and always provides **File Information** for a selected
file/folder: path, name, extension/size where applicable, modification time,
creation time when the filesystem exposes one, readability, and link targets.
Details use compact aligned label/value rows, muted labels, selectable plain-text
values and wrapping for long paths/descriptions. Information tabs scroll vertically.
Preview icons come from the same per-path system icon provider as the file listing;
folder previews use a compact icon area instead of reserving cover-image space.
Unix change time is not mislabeled as creation time. Folder totals/counts are
calculated asynchronously without reading file contents or following links.
Refresh recalculates them; totals and thumbnails remain in memory.

Specialized File subclasses contribute behavior through GUI-independent hooks:

```python
from commonUtils.fileUtils import File
from commonUtils.filesystem import BrowserPanel, BrowserDetails, BrowserAction
from commonUtils.fileTypes.registry import register_file_type

class ProjectFile(File):
    def browser_panels(self):
        return (BrowserPanel('project.details', 'Project Information', self.load_details),)

    def load_details(self):
        return BrowserDetails(fields=(('Title', 'Example'),))

    def browser_actions(self, context):
        return (BrowserAction('project.edit', 'Edit Project Data',
                              lambda ctx: ctx.invoke('project.edit', ctx.selection),
                              source='Project'),)

register_file_type(ProjectFile, 'project')
browser = FileBrowser(Path('/path/to/library'),
    services={'project.edit': edit_selected_project_files})
```

Context menus put built-in Open/Reveal actions first, then group contributed actions
under their `BrowserAction.source` feature name. Supply a user-facing name such as
`Comics` or `Project`; older descriptors without a source appear under `Extensions`.
Actions also expose the source through a tooltip and QAction property. Contributions
are collected from every selected object and each action provider, deduplicated by
key, and retain provider order within each feature group. Right-clicking an item
outside the selection uses only that item. Action callbacks receive the captured
selection; features decide which selected objects they support.

Applications can install reversible browser extensions with
`browser.install_extension(owner, services={...}, action_providers=(...), folder_fields=...)`.
`set_extension_enabled(owner, False)` removes that layer's handlers/providers/fields;
`True` restores it. `remove_extension(owner)` removes its registration permanently.
Layers preserve install order and restore underlying handlers after disabling a
later overlapping layer. The browser refreshes previews and totals after changes.
These APIs manage browser capabilities, not controller/worker lifetimes; the host
retains those objects until existing jobs and windows finish.

Register types during application startup, before the first listing/browser use.
This is a guideline, not enforced. The registration remains available throughout
that process to every subsequent resolver and `Directory.list_files()` call.
Existing File instances retain their class; the browser re-resolves cached objects
when the registry revision changes. Domain classes live in the consuming project.

Panel loaders return `BrowserDetails(fields, thumbnail, message, payload)` and run
on a worker thread; do not access widgets from them. Generic information stays
available even if a contributed panel fails. Every applicable contributed panel
appears alongside File Information as a tab; panels cannot be interactively hidden. Optional `payload` lets the application retain
its loaded domain document through the `details_loaded` signal.

Action callbacks and `browser_activate(context)` run on the GUI thread.
`BrowserContext.selection` contains File/Directory objects; `context.widget` is the
browser, and `context.invoke(name, *args)` calls an application-supplied service.
Return True from activation when the type handles double-clicks; False uses the
default application. Implement `browser_has_thumbnail = True` and
`browser_thumbnail(size) -> bytes` to provide tile images without a format-specific
branch in the browser. Thumbnail hooks run off the GUI thread and use a bounded
128-item cache. The size argument is a physical-pixel bounding box, including the
display scale; return enough pixels within that box for sharp high-DPI rendering.
The tile **Size** control applies to folder icons, application icons and thumbnails.
All render within the selected bounds, preserve their aspect ratio, and keep captions
aligned. Extra viewport space widens the cells without enlarging the icons.
Cached covers are regenerated when a larger icon size or higher display scale requires
more pixels. Selected-panel thumbnails likewise retain physical resolution. Constructors and detection rules should stay cheap and avoid
loading full metadata until requested.

Every browser enables Cut, Copy, Paste and inline Rename by default, with native
clipboard shortcuts and F2. A slow second click edits the selected filename;
the basename is selected without its extension. Paste appears on folders and empty
view backgrounds, targeting that folder; it is omitted for individual files.
Transfers run in the background, preserve links, and use numbered copy names for
collisions instead of overwriting. Cut entries leave the clipboard only after
successful moves. Cancellation stops between items.

Menus order opening, clipboard actions, Rename, contributed tools and OS-specific
Reveal. `BrowserAction(category='rename')` places a command beside Rename;
`order` (default 100) orders commands and their feature groups. Directory menus
include Open; file menus offer default-application opening. Double-clicking a folder
navigates into it.
An optional `action_providers=(provider,)` argument allows application-level actions
for Directory objects or mixed selections; providers receive `(item, context)` and
return BrowserAction descriptors. `folder_fields(directory, stats)` may contribute
additional count fields using `stats.extension_counts`, without hardcoding project
formats into shared folder scanning.

Useful integration methods/signals: `selected_objects()`, `context_menu_for(index)`,
`refresh()`, `refresh_item(path)`, `selection_changed(objects)`, `details_loaded(result)`
and `refreshed()`. Actions should call refresh_item after saving their data.
Panel preferences are local to the widget. Neither selections nor file metadata
are persisted by the shared browser.

Close owners safely: `stop()` cancels queued work and returns whether workers are
still finishing. If True, hide/defer owner destruction until the `idle` signal;
otherwise close normally. `shutdown()` waits for workers during application exit.
Do not delete a browser while a panel/thumbnail operation is running.


### File browser organization

| Module | Responsibility |
| --- | --- |
| `file_browser/__init__.py` | Browser integration, context actions, panel loading and worker lifecycle. |
| `file_browser/model.py` | Qt filesystem indexes resolved to registered File/Directory objects. |
| `file_browser/views.py` | Selection and location shared across views; thumbnail worker scheduling. |
| `file_browser/tiles.py` | Immediate grid layout, compact folder cells and folder-icon sizing. |
| `file_browser/columns.py` | Column trails, small chevrons and preview-column compatibility. |
| `file_browser/thumbnails.py` | Bounded thumbnail cache, invalidation and physical-pixel requirements. |
| `file_browser/controls.py` | View icons, folder-size menu and navigation buttons. |
| `file_browser/navigation.py` | Root-bounded breadcrumbs and Back/Forward history. |
| `file_browser/details.py` | Aligned, selectable information fields. |
| `ui/operations.py` | Generic background callbacks and completion signals, shared by browser and non-browser UI. |

Tile sizing uses logical pixels for layout and physical pixels for rendering.
The folder-size control changes system folder icons without shrinking covers in
mixed directories. Folder-only directories also use tighter cells and rows.
Constructing or changing a view never reads file contents; registered thumbnail
and panel hooks do that work in background operations.


## Markdown reader

The [Markdown viewer/editor guide](markdown/README.md) covers preview-only defaults,
explicit editing opt-in, typed Markdown formatting, properties, navigation and saving.
Public imports remain `from commonUtils.ui.markdown import MarkdownViewer, open_markdown`.
FileBrowser opts into editing; documentation callers get preview-only windows by default.

## Plain-text files

`from commonUtils.ui.text_editor import TextFileEditor` provides an embeddable UTF-8
file editor (`TextFileEditor(path, parent=None)`). Its `save()`, `reload()` and
`can_close()` methods support explicit atomic saving and unsaved-change prompts.
It preserves BOM/newline conventions and refuses to overwrite external changes.
Hosts should call `can_close()` before destroying it. The `saved(path)` signal
allows consumers to refresh configuration. It renders text directly without
interpreting INI sections or keys.

## Shared navigation settings

`commonUtils.settings.settings_path()` locates `ui/settings.ini` beside the browser
package. Logistics exposes this file under **Settings → commonUtils** using the
plain-text editor. Saves apply to existing comic readers on the next wheel event.
`get_setting(section, key, default, minimum=None, maximum=None)` reads bool, int,
float or string values using the default's type (bounds are keyword arguments).
`get_wheel_navigation_settings()` returns immutable validated wheel preferences.
Both accept a keyword `path` override for other hosts/tests. Missing, unreadable,
malformed or invalid settings use defaults; reads never rewrite the INI. File
identity timestamps cache parsing and invalidate it after edits.

The `[WheelNavigation]` defaults are `immediate_notches=true`, `sensitivity=20`
(range 1–100), and `cooldown_ms=250` (range 0–2000). Each vertical angle-only wheel
event with no scroll phase turns one page regardless of delta magnitude. Smooth
pixel/phase events accumulate to 60 pixels or 120 angle units divided by sensitivity,
with a cooldown to avoid bursts. Disable immediate notches to apply the smooth
threshold and cooldown to all wheels. Loading, modifiers and modal dialogs still
block navigation. These preferences affect discrete page navigation, not ordinary
file-browser list scrolling.

`FileBrowser(..., calculate_folder_sizes=False)` skips automatic recursive size/count
scans for large roots. `set_folder_sizes_enabled(True)` starts totals on demand;
disabling requests cancellation and drops cached totals. The default stays enabled
for existing consumers. Directory listings and feature actions remain available.


## Document workspaces, discovery and process execution

`commonUtils.ui.workspace.Workspace(factory)` hosts cooperative document views in
native Qt dock tabs. Views may provide `view_title`, `title_changed`, `idle`, and
`prepare_close()`. Each view owns its state. Tab headers share their group's width,
with a close button on the left of each tab and a small **+** after the tabs.
Right-clicking a header offers **Close tab**. New/close keyboard shortcuts remain
available, including when no tabs are open. Native tab dragging remains supported.
The former action toolbar is removed; `detach_active()`, `reattach_active()`,
`arrange(dock, placement)` (left/right/tabs), and `adopt(dock)` remain available
in code for floating, splitting, combining and transferring existing views.
Empty workspaces provide a full-size native dock anchor and a **+** button;
the anchor disappears after a real view returns. `reattach_active()` returns a
floating view without requiring a drag, even when no tabs remain docked.
Detached views also accept native top-edge drops. Once Qt finishes the drop,
the returning view joins the existing tab group (or fills an empty workspace)
instead of leaving a separate top split. Left/right docking remains available.
New tabs are grouped only with docked views, leaving detached views independent.
Call `prepare_close()`
before destroying an embedded workspace; it waits for all views' workers.

`commonUtils.directory_index` supplies immutable `Entry`/`Snapshot` metadata,
case-insensitive partial name search, and `storage_totals()`. `DirectoryCache`
persists completed and partial indices in SQLite, without entry/root count limits.
`directory_index_path()` defaults to:

- macOS: `~/Library/Caches/commonUtils/directory-index.sqlite3`
- Windows: `%LOCALAPPDATA%/commonUtils/directory-index.sqlite3`
- Linux: `$XDG_CACHE_HOME/commonUtils/directory-index.sqlite3` (default `~/.cache`)

One database holds every indexed root and recursion scope. SQLite can also create
`-wal` and `-shm` files while connections are open; a `directory-index.lock` file
serializes writers across windows/processes. No source file contents are stored.
`DirectoryCache(database=path)` selects a different database for another host/test.
The index storage folder is excluded from its own scans. Root symlinks retain
lexical result paths; nested symlinks/junctions are listed without traversal.

Each completely enumerated folder is a durable checkpoint. Entries are committed
in batches inside very large folders, but an interrupted folder must be enumerated
again. Cancelling leaves the completed-folder checkpoints and last complete index
intact. `get()` resumes pending work, revalidating saved folders/files before reuse
and reconciling additions, removals, replaced links and changed metadata. Unreadable
or changing folders produce a clearly marked partial snapshot and remain retryable.
`get(..., refresh=True)` discards pending work and rebuilds; `clear(root)` removes
overlapping indices. `invalidate(root)` requests an update on the next operation
without blocking the GUI thread. Cancellation is cooperative between filesystem
calls, and also interrupts long SQLite queries and waits for another writer.

Snapshots expose a read-only sequence of entries backed by SQLite. Iteration and
storage aggregation stream rows; name filtering/paging runs in SQL. Existing open
snapshots remain consistent during rebuilds/clears via SQLite read transactions.
These readers can retain WAL data until their result windows release old snapshots.
The database reuses freed space rather than imposing a fixed entry limit.

Search shows 500 results per page, with all matches available through Previous/Next.
Column sorting applies to the entire match set before paging.
It checks folder membership before reuse (`validate_files=False`); displayed file
sizes retain the scan timestamp. Storage analysis additionally checks file metadata
and computes totals on its worker. Rebuild requests fully fresh metadata. Search
and storage share **Rebuild index**/**Clear saved index** controls; a normal search
or **Analyze / Resume** continues saved work. The index path appears in the snapshot
status tooltip. Dialogs participate in browser cancellation/shutdown, and snapshot
dates/partial-state labels distinguish indexed results from a live filesystem view.
Browser modification dates use `filesystem.format_datetime()` consistently.

`commonUtils.ui.process_runner.ProcessRunner` executes argument vectors through
QProcess with incremental UTF-8 output, actual exit status, cooperative cancellation,
and optional whole-process retries. A process-specific parser returns
`ProcessUpdate` objects for stats and internally managed retry attempts.
`ProcessProgressWindow` presents these signals without owning command-specific
logic. `open_process()` retains modeless windows, including their final result;
application hosts call `prepare_close_all(retry_close)` before closing. Success
requires a normal zero exit; cancellation and failed starts remain distinct outcomes.


## Shared temporary storage

`commonUtils.storage.cache_directory()` resolves/creates the persistent cache
area using macOS Library/Caches, Windows LOCALAPPDATA, or Linux XDG_CACHE_HOME
(with ~/.cache fallback; relative XDG paths are ignored). `temporary_directory()`
creates its disposable `Temp` subdirectory. `temporary_workspace()` returns a
private, automatically cleaned TemporaryDirectory there. Use `create=False` for
side-effect-free path resolution. Persistent caches are never deleted on exit.
Destination-side staging remains beside the destination for atomic replacement.

On first use of the default SQLite index at its new location, a transactional
SQLite backup migrates the former Application Support/XDG data location, including
committed WAL data and partial checkpoints. The original remains for recovery and
older running applications. Existing canonical caches are never overwritten;
explicit `DirectoryCache(database=...)` paths are not migrated.

## Opt-in Slate appearance

`from commonUtils.ui.theme import apply_theme` then `controller = apply_theme(app)`
opts an existing QApplication into the shared Fusion palette and stylesheet.
Imports and other commonUtils consumers keep their current appearance. Modes are
`system` (default), `light`, and `dark`; `controller.set_mode(mode)` changes the
appearance immediately, and system mode follows Qt's OS color-scheme notifications.
`[Theme] mode=...` in the shared settings INI supplies the startup preference.
Logistics opts in at launch and offers a live Appearance selector in commonUtils
settings. The INI editor retains explicit saving and existing wheel preferences.
Selected tabs combine a contrasting surface, bold text and palette accent underline,
including workspace headers and native grouped dock tabs. Standard selection pairs
and ordinary/muted text meet WCAG 4.5:1 contrast in both palettes.
