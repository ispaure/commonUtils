# Adding a feature

Use `register() -> Feature(...)` as the single author-facing declaration. It combines
owned file types, browser actions, double-click activation, folder fields, optional
controller construction and initialization metadata. Declarations do not create Qt
widgets or register formats during discovery.

For a command shared by multiple feature declarations, the optional
`SelectionAction.shared_key` supplies one browser-menu identity. Declare the
same key, accepted types and routing behavior on each participating action so
the command works regardless of which selected type contributes it first.
Without this field, the usual `<feature id>.<action id>` identity is preserved.

Desktop readers can reuse `commonUtils.ui.reader_menus.ReaderMenus` for
File/Edit/View/Navigate menus and platform-standard shortcuts. The caller supplies
callbacks and adds format-specific navigation actions. `RecentFiles` stores up
to 40 canonical paths atomically under `commonUtils/Cache/Readers/recent.json`;
menus show at most 12 existing files matching the reader's suffixes. Pass a
custom history object/path for an isolated application or tests. The history
stores paths only, and a read/write failure does not prevent reading a file.

`commonUtils.ui.reader_chrome` provides presentation shared by separate readers:
`reader_button` builds consistently sized, keyboard-accessible controls;
`ReaderLabel` elides long titles/status visually while retaining full text and a
tooltip; `ReaderFullscreen(owner, action)` synchronizes the checked action and
icon with native window state and restores previous maximization. Call `toggle`
and `leave` from the reader's own commands. It does not install navigation keys
or choose content formats. Hosts can use the shared margins/spacing constants
and retain their existing widget handles.

## Runnable example: add a menu action to a browser

Save this as `project_browser.py` in your consuming project and run
`python project_browser.py /path/to/folder`, with commonUtils on the import path
and PySide6 installed. It adds **Project → Show selected paths**, including for
ordinary files and folders, without needing a custom file type. The same handler
works for mixed selections.

```python
from pathlib import Path
import sys
from commonUtils.features import Feature, BrowserExtension, SelectionAction
from commonUtils.fileUtils import File
from commonUtils.dirUtils import Directory
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser

def show_paths(context):
    context.host.statusBar().showMessage(
        ' | '.join(str(path) for path in context.paths))

feature = Feature(
    id='project', label='Project',
    browser=BrowserExtension(actions=(SelectionAction(
        id='show_paths', label='Show selected paths',
        accepts=(File, Directory), handler=show_paths,
    ),)),
)

class BrowserWindow(qt.QMainWindow):
    def __init__(self, root):
        super().__init__()
        self.setWindowTitle('Project Browser')
        feature.register_types()  # Before the first listing.
        self.browser = FileBrowser(root, parent=self)
        self.setCentralWidget(self.browser)
        self.binding = feature.install_browser(self.browser, host=self)
        self.browser.idle.connect(self.close)
        self.resize(1000, 700)

    def closeEvent(self, event):
        # This example has no controller jobs; wait for browser workers.
        if self.browser.stop():
            event.ignore()
        else:
            super().closeEvent(event)

if __name__ == '__main__':
    app = qt.initialize_q_app()
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    window = BrowserWindow(root)
    window.show()
    sys.exit(app.exec())
```

The handler runs on the GUI thread. Use
[OperationProgress](RECIPES.md#run-a-cancellable-job-in-a-qt-dialog) when an action
needs expensive filesystem work. Register your declarations once and retain the
bindings/controllers while their windows are alive. If you add a controller,
close handling must also wait for its jobs (see below).

## Add a format, preview panel and double-click handler

Replace the first example’s `feature = Feature(...)` block with the code below.
Place it before `BrowserWindow`, so the declaration exists when the window is built.
Create an `example.project` file to see its panel and actions. In a real project,
replace the sample details/editor with domain-specific loading and UI. Keep file
constructors and detection rules cheap; panel loaders run off the GUI thread.

```python
from commonUtils.features import (
    Feature, FileType, BrowserExtension, SelectionAction, FileActivation,
)
from commonUtils.fileUtils import File
from commonUtils.dirUtils import Directory
from commonUtils.filesystem import BrowserPanel, BrowserDetails

class ProjectFile(File):
    def browser_panels(self):
        return (BrowserPanel('project.details', 'Project Details', self.details),)

    def details(self):
        return BrowserDetails(fields=(('Name', self.file_name),))

    # Optional: browser_has_thumbnail = True and browser_thumbnail(size).

def edit(context):
    # Replace with your editor; parent dialogs to context.host.
    print('Edit these paths:', context.paths)

def open_project(context):
    print('Open this file:', context.path)

def counts(directory, stats):
    return (('Project files', stats.extension_counts.get('project', 0)),)

def register():
    return Feature(
        id='project',
        label='Project',
        file_types=[FileType(ProjectFile, extensions=('project',))],
        browser=BrowserExtension(
            actions=[SelectionAction(
                id='edit', label='Edit Project Data',
                accepts=(ProjectFile, Directory), handler=edit,
            )],
            activation=[FileActivation(ProjectFile, handler=open_project)],
            folder_fields=counts,
        ),
    )

feature = register()
```

There is no separate action-service string to wire up. The framework makes the menu
key `project.edit`, uses `Project` as its section heading, and calls the declared
handler with the supported selection. Action ids must be unique within a feature.

## What belongs where?

| Declaration/hook | Responsibility |
| --- | --- |
| `Feature.file_type_overrides` | Explicit subclass replacements of existing file types; [example](fileTypes/README.md#replace-an-existing-type-with-your-subclass). |
| `Feature.file_types` | Resolve extensions/detectors to your File classes, with feature ownership and priority. |
| `File.browser_panels()` | Load format-specific information. Generic File Information remains available. |
| `File.browser_has_thumbnail` / `browser_thumbnail(size)` | Produce format-specific thumbnails, with physical-pixel sizing. |
| `BrowserExtension.actions` | User operations on accepted files, folders or mixed selections. |
| `BrowserExtension.activation` | Double-clicked-file behavior. First matching declaration wins; folders always navigate. |
| `BrowserExtension.folder_fields` | Additional folder information, using shared scan results. |
| `BrowserExtension.create_controller` | Construct optional per-window state, workers and dialog management. |
| `Feature.initialize` | Optional application startup work; the host controls initialization order and frequency. |
| `Feature.requires` / `optional_requires` | Dependency metadata interpreted by the application host. |

Panel/thumbnail loaders run on browser workers and must not access widgets. Action
and activation handlers run on the GUI thread. Keep expensive work in your own
workers; declaring an action does not make its handler asynchronous.

## Handler context

Handlers take one `ActionContext`, exported from `commonUtils.features`:

| Field/property | Value |
| --- | --- |
| `selection` | Tuple of accepted File/Directory objects, in selection order. |
| `paths` | Tuple of paths for those objects. |
| `item`, `path` | Single selected object/path; raises if there are multiple objects. Activation always has one. |
| `browser` | The FileBrowser widget. |
| `host` | Its owning window, or the explicitly supplied host. Use as the dialog parent. |
| `controller` | The per-window controller, or `None` when no controller is needed. |

An action appears when a selection includes an accepted object. Other selected
objects are filtered out before its handler runs. Right-clicking an unselected item
uses that item alone. Repeated contributions across selected objects produce one
menu entry. Selection expansion into a folder's descendants remains the handler's
responsibility; the framework does not automatically recurse or change files.
After saving, call `context.browser.refresh_item(path)` or `refresh()` as appropriate.

## Hide an action when its prerequisites are missing

`SelectionAction.is_available(context)` is optional. It is evaluated against one
accepted item while building the context menu, so it must be cheap and must not
prompt, download software or modify files:

```python
SelectionAction(
    id='edit', label='Edit Project Data', accepts=ProjectFile,
    handler=edit, is_available=lambda context: context.path.is_file(),
)
```

A menu entry can still represent several accepted selected objects. Availability
does not replace handler validation: recheck all selected paths and prerequisites
when executing, since files and configuration may have changed after the menu opened.

## Application installation and toggles

The host creates QApplication/windows and consumes the feature declaration:

```python
feature = register()              # Retain this declaration for the session.
feature.register_types()          # Owned, idempotent process-wide registration.

# For each browser window:
binding = feature.install_browser(browser, host=window)

feature.set_enabled(False)        # Disable formats and every live browser binding.
feature.set_enabled(True)         # Restore rules, priority and browser capabilities.
```

The host enforces dependency rules and calls `initialize` before presenting the UI.
Feature discovery, an application Features page and dependency policy belong to
the consuming application. A host such as Logistics supplies them.

Repeated installation of the same declaration in the same browser returns its
existing binding. Each different window gets its own controller. Type registration
is process-wide; existing File objects keep their class, while browser refreshes
re-resolve objects after registry revisions. Declared actions precede the legacy
file-type activation hook; unmatched files retain default-application opening.

`binding.set_enabled(False)` disables only that browser's capabilities, leaving
global file-type resolution untouched. Use `feature.set_enabled` for a whole-feature
toggle. `binding.remove()` detaches that browser layer permanently and rejects stale
menu callbacks. Disabling does not stop existing controllers or undo initialization
side effects. Stale actions captured before a disable cannot invoke their handlers.

For a stateful feature, use `create_controller(host)` and handlers such as
`lambda context: context.controller.open_editor(context.paths)`. A controller may
supply `prepare_close() -> bool` and an `idle` Qt signal. The host must defer closing
while prepare_close returns false, retry on idle, and also respect FileBrowser's
`stop()/idle` worker lifecycle. An existing controller can be supplied explicitly
with `install_browser(browser, host=window, controller=window_controller)`.

## Lazy references and compatibility

`FileType.file_class`, `SelectionAction.accepts` and `FileActivation.accepts` can use
classes or deferred `package.module:Class` strings. Use deferred references when a
class imports an optional dependency: the application can inspect identity and
requirements without importing that class. Resolution happens during format
registration/browser installation, after the host checks dependencies.

The lower-level `register_file_type`, `install_extension`, services/providers and
file-type action hooks remain supported. They are useful for existing integrations
and special cases. New features should use a single declaration to avoid splitting
ownership, menu labels, accepted types and handler wiring across those APIs.

## Add thumbnails or keep per-window state

A format class can set `browser_has_thumbnail = True` and implement
`browser_thumbnail(size) -> bytes | None`. `size` is a physical-pixel bounding box;
return encoded image bytes sized for it. The browser decodes those bytes and keeps
a bounded memory cache. Loaders must not create or access Qt widgets, and a missing
thumbnail can return `None`. [The UI guide](ui/README.md#reusable-file-browser)
describes cache invalidation, panels and refresh signals.

Use `BrowserExtension(create_controller=factory)` when handlers need per-window
state. The factory receives the host and runs once for that window binding:

```python
def create_controller(host):
    return ProjectController(host)  # Your editor/job owner.

extension = BrowserExtension(
    create_controller=create_controller,
    actions=(SelectionAction('edit', 'Edit Project Data', ProjectFile,
        lambda context: context.controller.open_editor(context.paths)),),
)
```

The host owns shutdown. Check `binding.prepare_close()` and `browser.stop()`;
if the controller is busy, listen for `binding.idle` and retry, and if browser
workers are busy, retry on `browser.idle`. A controller's prepare_close should
request its chosen cancellation policy and return false until its jobs stop.
The browser's stop returns true while its own workers are still finishing.
Disabling a feature removes capabilities but does not destroy controllers or
cancel their existing jobs.
