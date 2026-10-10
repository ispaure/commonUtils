"""Route active view menus to native macOS bars and detached desktop headers."""
import sys
from . import pyside as qt
from shiboken6 import isValid


def sync_native_menus(container, document=None):
    if not isinstance(container, qt.QMainWindow):
        return
    native = sys.platform == 'darwin'
    # Attached views keep their in-page menus on Windows/Linux. Detached
    # containers expose the active document's menus in their own header.
    if not native and not getattr(getattr(container, 'workspace', None), 'is_detached', False):
        if isinstance(document, qt.QMainWindow) and isValid(document):
            document.menuBar().setNativeMenuBar(False)
            document.menuBar().show()
        return
    bar = container.menuBar()
    if not hasattr(container, '_workspace_base_menus'):
        container._workspace_base_menus = list(bar.actions())
    actions = container._workspace_base_menus
    if isinstance(document, qt.QMainWindow) and isValid(document):
        source = document.menuBar()
        source.setNativeMenuBar(False)
        source.hide()
        # PySide can transfer a QMenu wrapper's ownership to menuAction().
        # Retain these wrappers with the original bar, across tab switches and
        # container destruction, so accessing action.menu() cannot delete it.
        source._workspace_menu_actions = source.actions()
        actions = source._workspace_menu_actions
    for action in bar.actions():
        bar.removeAction(action)
    for action in actions:
        if isValid(action):
            bar.addAction(action)
    bar.setNativeMenuBar(native)
    bar.setVisible(bool(bar.actions()))
