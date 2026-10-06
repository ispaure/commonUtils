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

ui.display_msg_box_ok("Example", "Operation completed")

if ui.display_msg_box_ok_cancel("Example", "Continue?"):
    print("Continuing")
```

Set `ui.use_pyside` to control whether supported generic functions should attempt to use PySide first.

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

This backend requires the optional `PySide6` dependency.

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

A PySide application should initialize a `QApplication` once per project:

```python
from commonUtils.ui import pyside

q_app = pyside.initialize_q_app()
```

`initialize_q_app()` configures the Fusion style and applies platform-specific setup where required.

## Dependency

Most of `commonUtils.ui` does not require PySide6 when the native backend is used. Install `PySide6` only when the PySide-specific functionality is needed.

```text
PySide6
```

Because the backends are lazily imported, accessing the native UI does not unnecessarily import PySide.


## Reusable file browser

`commonUtils.ui.file_browser.FileBrowser` is an embeddable PySide widget for
folder/file browsing, selection, list/tile/column views, Back/Forward/Up navigation,
a parent-path selector, information tabs, thumbnails and context menus. It uses
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

Create a QApplication before the widget. Project-specific controls, such as a
library dropdown, belong outside this widget. `set_directory(Directory_or_Path)`
sets its navigation boundary; `navigate(path)` moves within that root. The right
panel remains visible and always provides **File Information** for a selected
file/folder: path, name, extension/size where applicable, modification time,
creation time when the filesystem exposes one, readability, and link targets.
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
                              lambda ctx: ctx.invoke('project.edit', ctx.selection)),)

register_file_type(ProjectFile, 'project')
browser = FileBrowser(Path('/path/to/library'),
    services={'project.edit': edit_selected_project_files})
```

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
128-item cache. Constructors and detection rules should stay cheap and avoid
loading full metadata until requested.

Generic context menus provide default-application opening and OS-specific Reveal.
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
