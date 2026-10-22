# Desktop UI building blocks

Use these widgets in your own Qt application. Create one QApplication before
constructing widgets, retain worker owners until they finish, and keep expensive
file or command work off the GUI thread.

For shared workflows, see the [user guide directory](../README.md#shared-component-user-guides).
For integration contracts, start at the [developer hub](../docs/developer/README.md).

## PySide application setup

Install PySide6, then initialize the application once:

```python
from commonUtils.ui import pyside as qt

app = qt.initialize_q_app()
window = qt.QMainWindow()
window.setWindowTitle('My tool')
window.resize(800, 600)
window.show()
app.exec()
```

## Reusable file browser

Start with the [complete browser window example](features/README.md#runnable-example-add-a-menu-action-to-a-browser).
It opens a folder and adds your own context-menu action. The
[feature guide](features/README.md) then shows custom file types, information
panels, double-click handlers and thumbnails.

The [browser guide](file_browser/README.md) covers navigation, search, storage
views and embedding. Browser workers load previews and directory metadata;
your action handlers still run on the GUI thread unless you schedule a worker.

## Background work and downloads

Use [OperationProgress](operation_progress.md) to run cancellable work and show
progress. Its runnable example includes safe close handling. For streamed external
processes, use `tasks.process_runner.ProcessRunner` and `tasks.process_progress.ProcessProgressWindow`;
[command execution](../integrations/wrappers/cmdShellWrapper/README.md) covers the
non-Qt alternative. [Streams](../runtime/streams/README.md) handles copying and hashing.

## Readers and editors

| Component | Guide |
| --- | --- |
| Markdown reader, source/formatted editing | [Markdown](markdown/README.md) |
| Code editing, gutters and syntax | [Code editor](code_editor/README.md) |
| Plain UTF-8 editor and INI settings editor | [Configuration](../configuration/README.md), [user guide](user_docs/README.md) |
| Archive contents and member selection | [Archive view](archive_view/README.md) |
| Shared reader menus, fullscreen controls and recent paths | [Browser features](features/README.md) |

The plain editor exposes `save()`, `reload()` and `can_close()`. Ask `can_close()`
before removing an editor so it can offer Save, Discard or Cancel. Readers can
open independently or through a consumer's document host.

## Reusable docking workspaces

A `Workspace` hosts widgets as dockable tabs. Supply a widget factory and let each
view decide whether it can close. The [workspace and presentation guide](workspaces.md)
covers worker lifetime, native floating panes, outlines, notifications and document
hosting.

## Indexed search in the browser

See [the browser guide](file_browser/README.md). The [index reference](../filesystem/index/README.md)
explains persistence, partial results and cancellation.

## Selection preview

See [the browser guide](file_browser/README.md). File classes supply read-only
panels; applications supply editing actions separately.

## Shared navigation settings

[Configuration](../configuration/README.md#shared-navigation-settings) describes
wheel preferences. Browser indexing uses event-driven updates and explicit refresh; ordinary browsing
remains available. Pause methods are programmatic APIs, not visible controls. See the [index reference](../filesystem/index/README.md).

## Opt-in Slate appearance

```python
from commonUtils.ui.appearance.theme import apply_theme

controller = apply_theme(app)
controller.set_mode('dark')  # 'light' or 'system' also work.
```

The theme applies only when requested. System mode follows OS appearance;
`[Theme] mode=...` in the shared settings INI chooses its starting mode.

## Backends and diagnostics

For scripts without Qt, select the native message-box backend explicitly:

```python
from commonUtils import ui

ui.use_pyside = False
ui.display_msg_box_ok('My tool', 'Finished')
```

Qt callers import `commonUtils.ui.pyside` and initialize QApplication first.
Workers must not open dialogs or touch widgets. Shared workers capture failures
under noninteractive logging and return them to their GUI owner. Critical
[diagnostics](../runtime/diagnostics/README.md) raise `DebugException`.

[Library overview](../README.md)

## Styling and settings layers

See [shared styling](styling.md) for the four font roles, accent and dark tint,
application opt-in, and central-settings navigation callback. `[Styling] theme_mode`
is the preferred theme source; `[Theme] mode` remains a fallback for older hosts.
See [layered configuration](../configuration/README.md#software-defaults-and-sparse-personal-overrides)
for the resettable software/personal editor and host-owned path registration.

## Module organization

Implementations are grouped by responsibility. Use the grouped module paths for
imports and mock patch targets; former flat forwarding modules have been removed.
The UI facade and these packages preserve lazy Qt loading. Shared configuration
continues to live at `ui/settings.ini`.

- [Docking workspaces](workspaces/README.md): Docking, tab gestures, splitting, floating windows and native workspace menus.
- [Background task presentation](tasks/README.md): Qt workers, cancellable operation progress, streamed processes and download dialogs. Runtime operations and streams remain outside the UI layer.
- [Shared reader controls](readers/README.md): Reader menus, fullscreen controls, read-aloud presentation and wheel navigation shared by document readers.
- [Settings editor widgets](settings/README.md): Typed INI editors, layered overrides, settings sections and font previews. Parsing, persistence and host-owned paths remain in configuration.
- [Shared UI appearance](appearance/README.md): Opt-in themes, live font styling and palette-aware painted icons.
- [Optional native Toga components](native/README.md): Configurable destinations, native Back routing, chrome restoration and image gestures. Consumers supply workflows and package the Android bridges.
- [Qt resource windows](resources/README.md): provider-backed browsing, Open/Save As,
  text editing and retained operation ownership. Portable storage contracts live
  in [runtime resources](../runtime/resources/README.md).
