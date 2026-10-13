# PySide backend

Qt application setup, windows, common widgets, messages and progress dialogs. This is the canonical PySide backend; import it directly as `commonUtils.ui.pyside`.

Create a `QApplication` before creating widgets. Requires PySide6. Import `from commonUtils.ui import pyside as qt`.

`initialize_q_app()` installs a value-wheel policy for the whole application.
Wheel gestures over spin boxes (integer, floating point, date and time), closed
dropdowns, sliders and dials scroll the containing scroll area without changing
values, including focused controls and embedded line edits. Typing, keyboard
arrows and clicks retain their normal behavior. Open dropdown lists and scrollbars
still scroll. The policy covers existing/future widgets and direct PySide6 imports.
Hosts creating their own QApplication can call
`commonUtils.ui.pyside.wheel_policy.install_value_wheel_policy(app)`;
installation is idempotent. Shared INI and layered settings editors also install
it when constructed. Without a containing scroll area, these value controls
ignore wheel gestures.

On Windows, `initialize_q_app()` also installs `WindowDpiScaleFixer` once for the
application. It observes native DPI and move/resize messages, saves the logical
client QSize before a monitor crossing, and restores either dimension if it
drifts after Qt processes the change. Qt retains control of display scaling,
position and frame margins. Native resize gestures cancel a pending repair;
maximized/minimized/fullscreen windows and popups retain native sizing. Queued
repairs are cancelled when a window is destroyed.

Hosts constructing their own QApplication may call
`qt.install_window_dpi_scale_fixer(app)`; it returns the existing helper on Windows
and `None` on other platforms. Call `helper.close()` to uninstall it. The policy
does not change point sizes or address default-font differences between platforms.
Tests exercise real widgets with synthetic native Windows message sequences;
physical mixed-DPI monitor transitions still require Windows hardware validation.

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [__init__.py](__init__.py) | Qt facade, organized into focused implementation modules. |
| [_imports.py](_imports.py) | Package exports and imports. |
| [application.py](application.py) | Application utilities; public API is commonUtils.ui.pyside. |
| [wheel_policy.py](wheel_policy.py) | Application-wide wheel protection for value controls. |
| [window_dpi.py](window_dpi.py) | Windows-only preservation of logical window sizes across DPI changes. |
| [messages.py](messages.py) | Messages utilities; public API is commonUtils.ui.pyside. |
| [progress.py](progress.py) | Progress utilities; public API is commonUtils.ui.pyside. |
| [widgets.py](widgets.py) | Widgets utilities; public API is commonUtils.ui.pyside. |
| [windows.py](windows.py) | Windows utilities; public API is commonUtils.ui.pyside. |

[Parent guide](../README.md)

This is the desktop Qt facade, including its existing file-dialog exports.
Explicit import on iOS/Android raises `UnsupportedCapabilityError` before loading
Qt binaries. Portable document/file modules do not import this facade; a mobile
UI and document picker remain future host integrations.
