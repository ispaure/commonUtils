# Adding a feature

Use `register() -> Feature(...)` as the single author-facing declaration. It combines
owned file types, browser actions, double-click activation, folder fields, optional
controller construction and initialization metadata. Declarations do not create Qt
widgets or register formats during discovery.

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
```

There is no separate action-service string to wire up. The framework makes the menu
key `project.edit`, uses `Project` as its section heading, and calls the declared
handler with the supported selection. Action ids must be unique within a feature.

## What belongs where?

| Declaration/hook | Responsibility |
| --- | --- |
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
commonUtils does not discover application plugins, create an application Features
page, or implement dependency policy. Logistics provides those pieces.

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
