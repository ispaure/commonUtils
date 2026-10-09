"""Reusable Qt dock-backed document tabs with cooperative view shutdown."""
from . import pyside as qt


class WorkspaceDock(qt.QDockWidget):
    def __init__(self, workspace, view, title):
        super().__init__(title, workspace)
        self.workspace = workspace
        self.setWidget(view)
        self.setFeatures(qt.QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.setAllowedAreas(qt.Qt.DockWidgetArea.LeftDockWidgetArea | qt.Qt.DockWidgetArea.RightDockWidgetArea)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)

    def closeEvent(self, event):
        if not getattr(self.widget(), 'prepare_close', lambda: True)():
            event.ignore()
            return
        self.workspace.remove_view(self)
        event.accept()


class Workspace(qt.QMainWindow):
    """Views expose prepare_close() and idle; their application state stays in the view."""
    active_changed = qt.Signal(object)

    def __init__(self, factory, parent=None):
        super().__init__(parent)
        self.setWindowFlags(qt.Qt.WindowType.Widget)
        self.factory = factory
        self.docks = []
        self.active_dock = None
        self._closing = False
        self.setDockOptions(qt.QMainWindow.DockOption.AllowTabbedDocks)
        self.setTabPosition(qt.Qt.DockWidgetArea.AllDockWidgetAreas, qt.QTabWidget.TabPosition.North)
        self.toolbar = self.addToolBar('Views')
        self.toolbar.setMovable(False)
        self.new_action = self.toolbar.addAction('New tab', lambda: self.add_view())
        self.new_action.setShortcut(qt.QKeySequence('Ctrl+T'))
        self.new_action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.close_action = self.toolbar.addAction('Close tab', self.close_active)
        self.close_action.setShortcut(qt.QKeySequence('Ctrl+W'))
        self.close_action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)

    @property
    def active_view(self):
        return self.active_dock.widget() if self.active_dock else None

    def add_view(self, argument=None):
        if self._closing:
            return None
        view = self.factory(argument)
        dock = WorkspaceDock(self, view, getattr(view, 'view_title', 'View'))
        previous = self.active_dock
        self.docks.append(dock)
        self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        if previous:
            self.tabifyDockWidget(previous, dock)
        dock.visibilityChanged.connect(lambda visible: self._activate(dock) if visible else None)
        signal = getattr(view, 'title_changed', None)
        if signal is not None:
            signal.connect(dock.setWindowTitle)
        signal = getattr(view, 'idle', None)
        if signal is not None:
            signal.connect(lambda: self._retry_view_close(dock))
        dock.show()
        dock.raise_()
        self._activate(dock)
        return view

    def _activate(self, dock):
        if dock in self.docks:
            self.active_dock = dock
            self.active_changed.emit(dock.widget())

    def close_active(self):
        if self.active_dock:
            self.active_dock.close()

    def _retry_view_close(self, dock):
        if self._closing:
            self.window().close()
        elif getattr(dock.widget(), 'closing', False):
            dock.close()

    def remove_view(self, dock):
        self.docks.remove(dock)
        self.removeDockWidget(dock)
        if self.active_dock is dock:
            self.active_dock = self.docks[-1] if self.docks else None
            if self.active_dock:
                self.active_dock.raise_()
            self.active_changed.emit(self.active_view)

    def prepare_close(self):
        self._closing = True
        ready = True
        for dock in tuple(self.docks):
            if not getattr(dock.widget(), 'prepare_close', lambda: True)():
                ready = False
        return ready

    def closeEvent(self, event):
        if self.prepare_close():
            event.accept()
        else:
            event.ignore()
