# Desktop UI building blocks

Use these widgets in your own Qt application. Create one QApplication before
constructing widgets, retain worker owners until they finish, and keep expensive
file or command work off the GUI thread.

For shared workflows, see the [user guide directory](../../overview.md#shared-component-user-guides).
For integration contracts, start at the [developer hub](../../development.md).

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

Start with the [complete browser window example](features/features.md#runnable-example-add-a-menu-action-to-a-browser).
It opens a folder and adds your own context-menu action. The
[feature guide](features/features.md) then shows custom file types, information
panels, double-click handlers and thumbnails.

The [browser guide](file_browser/file_browser.md) covers navigation, search, storage
views and embedding. Browser workers load previews and directory metadata;
your action handlers still run on the GUI thread unless you schedule a worker.

## Background work and downloads

Use [OperationProgress](operation_progress.md) to run cancellable work and show
progress. Its runnable example includes safe close handling. For streamed external
processes, use `tasks.process_runner.ProcessRunner` and `tasks.process_progress.ProcessProgressWindow`;
[command execution](../integrations/wrappers/cmdShellWrapper/cmdShellWrapper.md) covers the
non-Qt alternative. [Streams](../runtime/streams/streams.md) handles copying and hashing.

## Readers and editors

| Component | Guide |
| --- | --- |
| Markdown reader, source/formatted editing | [Markdown](markdown/markdown.md) |
| Code editing, gutters and syntax | [Code editor](code_editor/code_editor.md) |
| Plain UTF-8 editor and INI settings editor | [Configuration](../configuration/configuration.md), [user guide](../../../user/components/components.md) |
| Archive contents and member selection | [Archive view](archive_view/archive_view.md) |
| Shared reader menus, fullscreen controls and recent paths | [Browser features](features/features.md) |

The plain editor exposes `save()`, `reload()` and `can_close()`. Ask `can_close()`
before removing an editor so it can offer Save, Discard or Cancel. Readers can
open independently or through a consumer's document host.

## Reusable docking workspaces

A `Workspace` hosts widgets as dockable tabs. Supply a widget factory and let each
view decide whether it can close. The [workspace and presentation guide](workspaces.md)
covers worker lifetime, native floating panes, outlines, notifications and document
hosting.

## Indexed search in the browser

See [the browser guide](file_browser/file_browser.md). The [index reference](../filesystem/index/index.md)
explains persistence, partial results and cancellation.

## Selection preview

See [the browser guide](file_browser/file_browser.md). File classes supply read-only
panels; applications supply editing actions separately.

## Shared navigation settings

[Configuration](../configuration/configuration.md#shared-navigation-settings) describes
wheel preferences. Browser indexing uses event-driven updates and explicit refresh; ordinary browsing
remains available. Pause methods are programmatic APIs, not visible controls. See the [index reference](../filesystem/index/index.md).

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
[diagnostics](../runtime/diagnostics/diagnostics.md) raise `DebugException`.

[Library overview](../../overview.md)

## Styling and settings layers

See [shared styling](styling.md) for the four font roles, accent and dark tint,
application opt-in, and central-settings navigation callback. `[Styling] theme_mode`
is the preferred theme source; `[Theme] mode` remains a fallback for older hosts.
See [layered configuration](../configuration/configuration.md#software-defaults-and-sparse-personal-overrides)
for the resettable software/personal editor and host-owned path registration.

## Module organization

Implementations are grouped by responsibility. Use the grouped module paths for
imports and mock patch targets; former flat forwarding modules have been removed.
The UI facade and these packages preserve lazy Qt loading. Shared configuration
continues to live at `ui/settings.ini`.

- [Docking workspaces](workspaces/workspaces.md): Docking, tab gestures, splitting, floating windows and native workspace menus.
- [Background task presentation](tasks/tasks.md): Qt workers, cancellable operation progress, streamed processes and download dialogs. Runtime operations and streams remain outside the UI layer.
- [Shared reader controls](readers/readers.md): Reader menus, fullscreen controls, read-aloud presentation and wheel navigation shared by document readers.
- [Settings editor widgets](settings/settings.md): Typed INI editors, layered overrides, settings sections and font previews. Parsing, persistence and host-owned paths remain in configuration.
- [Shared UI appearance](appearance/appearance.md): Opt-in themes, live font styling and palette-aware painted icons.
- [Optional native Toga components](native/native.md): Configurable destinations, native Back routing, chrome restoration and image gestures. Consumers supply workflows and package the Android bridges.
- [Qt resource windows](resources/resources.md): provider-backed browsing, Open/Save As,
  text editing and retained operation ownership. Portable storage contracts live
  in [runtime resources](../runtime/resources/resources.md).

## Pages

- [Native item browser](native_browser/native_browser.md)
- [PySide backend](pyside/pyside.md)
- [Virtual resource providers](resource-providers.md)
- [Project-confined tab gestures](scoped_tabs.md)
- [Anchor-relative dock placement](workspace_layout.md)

## Embedded HTML dropdowns

`ui.native.web_dropdown` exports offline `DROPDOWN_CSS` and `DROPDOWN_SCRIPT`
strings. Embed them once in a WebView document, then construct
`new WebDropdown(surface, trigger, {close, items})`. `items` defaults to the
surface; pass a command container when a surface also hosts other panels.
After making the surface visible, `activate()` assigns menu/menuitem roles,
updates the trigger and focuses the first visible enabled command. `deactivate()`
clears active navigation and the expanded state. The host owns showing/hiding,
outside-click dismissal, focus restoration and command execution; `close` must
perform that lifecycle. Arrow keys wrap and skip hidden/disabled commands;
Home/End select endpoints and Escape calls `close`.

Rows are borderless. Override `--dropdown-row-height`, `--dropdown-row-padding`
and `--dropdown-hover` for platform sizing and palette. High-contrast host styles
must preserve borderless `[role=menuitem]` rows while retaining visible keyboard
focus. Form controls in option panels remain distinct controls. Use native Qt,
UIKit or Android menus for native widgets; this component serves embedded HTML.
