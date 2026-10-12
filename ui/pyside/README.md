# PySide backend

Qt application setup, windows, common widgets, messages and progress dialogs. This is the canonical PySide backend; import it directly as `commonUtils.ui.pyside`.

Create a `QApplication` before creating widgets. Requires PySide6. Import `from commonUtils.ui import pyside as qt`.

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [__init__.py](__init__.py) | Qt facade, organized into focused implementation modules. |
| [_imports.py](_imports.py) | Package exports and imports. |
| [application.py](application.py) | Application utilities; public API is commonUtils.ui.pyside. |
| [messages.py](messages.py) | Messages utilities; public API is commonUtils.ui.pyside. |
| [progress.py](progress.py) | Progress utilities; public API is commonUtils.ui.pyside. |
| [widgets.py](widgets.py) | Widgets utilities; public API is commonUtils.ui.pyside. |
| [windows.py](windows.py) | Windows utilities; public API is commonUtils.ui.pyside. |

[Parent guide](../README.md)

This is the desktop Qt facade, including its existing file-dialog exports.
Explicit import on iOS/Android raises `UnsupportedCapabilityError` before loading
Qt binaries. Portable document/file modules do not import this facade; a mobile
UI and document picker remain future host integrations.
