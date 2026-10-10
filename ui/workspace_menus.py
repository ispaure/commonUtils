"""Route the active embedded document's menus through its native macOS window."""
import sys
from . import pyside as qt
from shiboken6 import isValid


def sync_native_menus(container, document=None):
    if sys.platform != 'darwin' or not isinstance(container, qt.QMainWindow):
        return
    bar = container.menuBar()
    if not hasattr(container, '_workspace_base_menus'):
        container._workspace_base_menus = list(bar.actions())
    actions = container._workspace_base_menus
    if isinstance(document, qt.QMainWindow) and isValid(document):
        source = document.menuBar()
        source.setNativeMenuBar(False)
        source.hide()
        actions = source.actions()
    for action in bar.actions():
        bar.removeAction(action)
    for action in actions:
        if isValid(action):
            bar.addAction(action)
    bar.setNativeMenuBar(True)
