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

### 📄 `pyside.py`

Provides the more complete PySide6 UI toolkit used for building application interfaces.

This backend requires the optional `PySide6` dependency and an existing
QApplication before creating any widget or showing a message box. The PySide
snippets below assume the application has performed the setup shown next.

```python
from commonUtils.ui import pyside

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
available even if a contributed panel fails. `BrowserPanel.default_enabled` sets
initial visibility; the **Panels** menu lets users show/hide contributed tabs.
The generic tab cannot be hidden. Optional `payload` lets the application retain
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
Cached covers are regenerated when larger cells or a higher display scale require
more pixels. Selected-panel thumbnails likewise retain physical resolution. Constructors and detection rules should stay cheap and avoid
loading full metadata until requested.

File context menus provide default-application opening and OS-specific Reveal.
Directory menus provide Reveal and contributed actions, without an Open in Default
App entry; double-clicking a folder navigates into it.
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

`commonUtils.ui.markdown` uses Qt's Markdown/rich-text renderer for headings, lists,
tables, fenced code, local images and links, without a web-engine dependency.
Documents open read-only. **Edit** enables same-pane formatted editing by default:
headings, emphasis, lists, links and tables remain rendered while editing. The
**Formatted / Source** selector also provides precise Markdown source editing.
**Read** returns to the rendered read-only document, including unsaved changes. Requires PySide6 and an existing
QApplication, as described above.

```python
from commonUtils.ui.markdown import MarkdownViewer, open_markdown

# Separate window; the helper retains it until closed.
window = open_markdown('docs/index.md', parent=application_window)

# Or embed the widget in an existing layout.
viewer = MarkdownViewer('docs/index.md', parent=application_window)
layout.addWidget(viewer)
```

`open_document(path, fragment='')` returns whether navigation succeeded.
`current_path` provides the displayed document path; `path_changed(Path)` signals
successful loads/saves (or `None` for a new untitled document). Relative file links resolve from the current document, including
encoded spaces and `#heading-fragments`. Headings receive GitHub-style anchors,
with duplicate headings suffixed `-1`, `-2`, and so on. Back/Forward (Alt+Left /
Alt+Right) restore document history and scroll positions. Navigating after going
Back discards the abandoned forward branch. Navigation buttons use the same native
Qt icons and shared control as FileBrowser.

**Contents** opens a floating list at the right side of the toolbar, with indented
headings/subheadings and links to their anchors. It closes after a selection, Escape,
or clicking outside. It reflects unsaved edits and heading jumps participate in
Back/Forward history in reading mode. Choosing a heading while editing formatted
text keeps that editing mode and moves its cursor to the heading. Choosing one
from source mode switches to reading without discarding edits.

### YAML properties (frontmatter)

A `---`-delimited YAML mapping at the very beginning of the document appears in a
**Properties** panel above the body, following
[Obsidian's frontmatter convention](https://obsidian.md/help/properties). Properties
are excluded from body rendering and the table of contents. Reading shows values;
formatted editing enables Add/Edit/Remove property, checkbox controls and **Edit
YAML…**. Source mode still exposes the complete file.

Supported property editors include text, lists/tags (one text item per line),
numbers, booleans, ISO dates and date-times. Nested mappings, non-text list items
and tagged/complex values remain raw and use the YAML/source editor. There is no vault-wide type registry,
Obsidian indexing or wiki-link resolution. Property names must be unique nonempty
strings. Dates use `YYYY-MM-DD`; date-times use ISO format.

Body edits preserve the frontmatter text, including comments and quoted/multiline
values. Editing a basic property patches only that property's lines; unrelated
fields, comments and the Markdown body remain unchanged. Complex values such as
nested maps, block scalars, anchors and tags are kept as raw YAML and can be edited
with **Edit YAML…** or Source mode. Invalid basic syntax is shown with an error and
retained during body edits. An unclosed block switches to Source mode so formatted
editing cannot swallow the rest of the document.

There is **no YAML dependency**. The built-in parser supports a deliberate subset:
plain/quoted text, true/false, null, decimal numbers, ISO dates/date-times, simple
inline lists and dash lists. It checks duplicate names and common syntax errors;
it does not fully validate complex YAML, resolve aliases, interpret custom tags,
or implement the complete YAML specification. Complex input stays raw rather
than being coerced into basic fields. Arbitrary object constructors are never run.

```python
from commonUtils.markdownUtils import split_frontmatter, parse_properties, replace_property

text = '---\ntitle: "Example"\ntags: [docs]\n---\n# Body\n'
parts = split_frontmatter(text)
assert parse_properties(parts)['tags'] == ['docs']
updated = replace_property(text, 'published', True)
assert split_frontmatter(updated).body == parts.body
```

### Editing and saving

Standalone windows provide File/Edit/View menus using the platform's normal menu
placement (the system menu bar on macOS). The toolbar does not display a filesystem path; the title uses the
document filename. Windows provide **File → New / Open / Save / Save As / Close** and an
Edit menu with Undo/Redo, Cut/Copy/Paste, Select All and Find/Replace. The widget owns reusable actions
(`new_action`, `open_action`, `save_action`, `save_as_action`, `find_action`, etc.)
that embedding applications can put in their own menus. Standard platform shortcuts
are enabled (Command on macOS); Ctrl+N, Ctrl+O, Ctrl+S, Ctrl+Shift+S and Ctrl+F
also work explicitly. Both editors support native selection, clipboard and undo/redo.
The formatting toolbar supplies bold, italic, inline code, links, headings, bullet
lists and quotes. Ctrl+B/Ctrl+I format text; Ctrl+K inserts a link. Find works in
reading and both editing modes; Replace/Replace all operate on the active editor. Search
is literal and case-insensitive; Replace all is one undo step.

```python
viewer.set_editing(True)  # Same-pane formatted editing is the default.
# viewer.formatted_editor is the editable QTextEdit.
viewer.set_edit_mode('source')  # Optional precise editing in viewer.editor.
# The toolbar formats rich text or inserts source syntax, depending on the mode.
if viewer.is_modified:
    saved = viewer.save_document()  # False on failure/cancel; inline error message.
# An explicit path performs Save As and updates the document's relative-link base.
saved = viewer.save_document('docs/revised.md')
```

`new_document()`, `open_document()` and `save_document()` return success booleans.
A modified document is marked with `*`; `modified_changed(bool)` reports changes.
Leaving a modified document or closing the standalone window prompts for
Save/Discard/Cancel. Reading mode and heading jumps retain unsaved edits in memory.
An embedding application's close handler should call `viewer.can_close()` and
honor a false result before destroying its parent window.

Formatted editing uses Qt's Markdown reader/writer. Entering formatted mode,
viewing contents or saving without changes does not reserialize the source: exact
original bytes are retained. Actual formatted edits convert the document back to
Markdown, so spacing, table alignment, list markers and code-fence spelling may
change. Raw HTML, comments, custom extensions and other unsupported syntax can be
lost during that conversion; use **Source** for documents whose precise syntax
matters. There is no full HTML editor or extension-aware round-trip guarantee.
Switching modes retains text and unsaved status; rebuilding the rich document
after source changes resets its rich undo history. `markdown_text()` returns the
current Markdown, synchronizing formatted edits into the source editor.

Saves stage a file beside the destination, flush it and replace atomically,
preserving existing mode bits. A failed save keeps the original and unsaved edits.
An observed on-disk change prevents saving over the loaded file; use Save As or
reopen. This check is not a filesystem lock and cannot exclude a write racing with
the final replacement. Symlink save destinations are refused. Unmodified saves
retain exact bytes; edited files use UTF-8, preserving a UTF-8 BOM and uniform
CRLF line endings when present. Editing may normalize other line endings or
Unicode line separators through Qt's plain-text editor. Saving is explicit:
there is no autosave.

HTTP/HTTPS and mail links open through the operating system's default application.
Local navigation accepts UTF-8 (optionally BOM-prefixed) `.md` and `.markdown`
files. Missing, unreadable, invalid-text or unsupported linked files show an inline
error while retaining the current page and history. Local non-Markdown files and
other URL schemes are not launched by this reader. Rendering is Qt Markdown;
full web-page HTML/CSS, JavaScript and Mermaid diagrams are not supported.

Internally, the public widget/window live in `markdown.py`; editing actions and
mode synchronization are separated from the properties panel. Shared heading
iteration keeps reading and formatted-editor anchors consistent, including names
that collide with generated numeric suffixes. Encoding and atomic file writes
live in a Qt-independent internal helper. Applications should keep using
`MarkdownViewer`, `MarkdownWindow` and `open_markdown` rather than these internals.

FileBrowser automatically uses this window for registered MarkdownFile activation;
applications may still supply a higher-priority activation handler. Keep feature
user documentation in the consuming application, not the shared library.
