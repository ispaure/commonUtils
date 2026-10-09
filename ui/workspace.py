"""Reusable Qt dock-backed document tabs with cooperative view shutdown."""
from . import pyside as qt
from weakref import WeakSet

_workspaces = WeakSet()


class WorkspaceDock(qt.QDockWidget):
    def __init__(self, workspace, view, title):
        super().__init__(title, workspace)
        self.workspace = workspace
        self.setWidget(view)
        self.setFeatures(qt.QDockWidget.DockWidgetFeature.DockWidgetClosable |
                         qt.QDockWidget.DockWidgetFeature.DockWidgetMovable |
                         qt.QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.setAllowedAreas(qt.Qt.DockWidgetArea.LeftDockWidgetArea | qt.Qt.DockWidgetArea.RightDockWidgetArea)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)

    def contextMenuEvent(self, event):
        self.workspace._activate(self)
        menu = qt.QMenu(self)
        menu.addAction('Detach into window', lambda: self.setFloating(True))
        menu.addAction('Dock left', lambda: self.workspace.arrange(self, 'left'))
        menu.addAction('Dock right', lambda: self.workspace.arrange(self, 'right'))
        menu.addAction('Combine as tabs', lambda: self.workspace.arrange(self, 'tabs'))
        attach = menu.addMenu('Attach to window')
        from shiboken6 import isValid
        for workspace in list(_workspaces):
            if isValid(workspace) and not workspace._closing:
                title = workspace.window().windowTitle() or 'File Browser'
                if workspace is self.workspace:
                    title += ' (current)'
                attach.addAction(title, lambda checked=False, target=workspace: target.adopt(self))
        menu.addSeparator()
        menu.addAction('Close view', self.close)
        menu.exec(event.globalPos())
        menu.deleteLater()

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
        self._drop_target = qt.QDockWidget('Return a detached tab', self)
        self._drop_target.setObjectName('workspace.emptyDropTarget')
        self._drop_target.setFeatures(qt.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self._drop_target.toggleViewAction().setVisible(False)
        self._drop_target.setAllowedAreas(qt.Qt.DockWidgetArea.LeftDockWidgetArea |
                                          qt.Qt.DockWidgetArea.RightDockWidgetArea)
        self._drop_target.setTitleBarWidget(qt.QWidget(self._drop_target))
        hint = qt.QLabel('Drop a detached tab here to return it to this window.\n'
                        'You can also click Reattach in the toolbar.')
        hint.setWordWrap(True)
        hint.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        hint.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)
        hint.setMinimumSize(200, 150)
        hint.setAccessibleName('Empty workspace docking area')
        self._drop_target.setWidget(hint)
        _workspaces.add(self)
        self.setDockOptions(qt.QMainWindow.DockOption.AllowTabbedDocks |
                            qt.QMainWindow.DockOption.AllowNestedDocks |
                            qt.QMainWindow.DockOption.GroupedDragging)
        qt.QApplication.instance().focusChanged.connect(self._focus_changed)
        self.setTabPosition(qt.Qt.DockWidgetArea.AllDockWidgetAreas, qt.QTabWidget.TabPosition.North)
        self.toolbar = self.addToolBar('Views')
        self.toolbar.setMovable(False)
        self.new_action = self.toolbar.addAction('New tab', lambda: self.add_view())
        self.new_action.setShortcut(qt.QKeySequence(qt.QKeySequence.StandardKey.AddTab))
        self.new_action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.close_action = self.toolbar.addAction('Close tab', self.close_active)
        self.close_action.setShortcut(qt.QKeySequence(qt.QKeySequence.StandardKey.Close))
        self.close_action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.toolbar.addAction('Detach', self.detach_active)
        self.reattach_action = self.toolbar.addAction('Reattach', self.reattach_active)
        self.reattach_action.setToolTip('Return the active detached tab, or another detached tab belonging to this window.')
        self.toolbar.addAction('Split left', lambda: self.arrange(self.active_dock, 'left'))
        self.toolbar.addAction('Split right', lambda: self.arrange(self.active_dock, 'right'))
        self.toolbar.addAction('Combine tabs', lambda: self.arrange(self.active_dock, 'tabs'))
        self._update_drop_target()

    def _hide_drop_target(self):
        self._drop_target.hide()
        self.removeDockWidget(self._drop_target)

    def _update_drop_target(self):
        """Give Qt a full-size native docking anchor when all real views are floating.

        Run after native docking completes: changing dock layout inside Qt's
        topLevelChanged signal would disturb an in-progress native drop.
        """
        floating = [dock for dock in self.docks if dock.isFloating()]
        self.reattach_action.setEnabled(bool(floating) and not self._closing)
        if self._closing or any(not dock.isFloating() for dock in self.docks):
            self._hide_drop_target()
        else:
            self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, self._drop_target)
            self._drop_target.show()

    def _docking_changed(self, floating):
        qt.QTimer.singleShot(0, self._update_drop_target)

    def _docked_anchor(self, excluding=None):
        if self.active_dock is not excluding and self.active_dock and not self.active_dock.isFloating():
            return self.active_dock
        return next((dock for dock in self.docks if dock is not excluding and not dock.isFloating()), None)

    @property
    def active_view(self):
        return self.active_dock.widget() if self.active_dock else None

    def add_view(self, argument=None):
        if self._closing:
            return None
        view = self.factory(argument)
        dock = WorkspaceDock(self, view, getattr(view, 'view_title', 'View'))
        previous = self._docked_anchor()
        self._hide_drop_target()
        self.docks.append(dock)
        self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        if previous:
            self.tabifyDockWidget(previous, dock)
        dock.topLevelChanged.connect(lambda floating: dock.workspace._docking_changed(floating))
        dock.visibilityChanged.connect(lambda visible: dock.workspace._activate(dock) if visible else None)
        signal = getattr(view, 'title_changed', None)
        if signal is not None:
            signal.connect(dock.setWindowTitle)
        signal = getattr(view, 'idle', None)
        if signal is not None:
            signal.connect(lambda: dock.workspace._retry_view_close(dock))
        dock.show()
        dock.raise_()
        self._activate(dock)
        self._update_drop_target()
        return view

    def _activate(self, dock):
        if dock in self.docks:
            self.active_dock = dock
            self.active_changed.emit(dock.widget())

    def _focus_changed(self, old, current):
        if current is None:
            return
        for dock in self.docks:
            if current is dock.widget() or dock.widget().isAncestorOf(current):
                self._activate(dock)
                break

    def detach_active(self):
        if self.active_dock:
            self.active_dock.setFloating(True)
            self.active_dock.show()

    def reattach_active(self):
        dock = self.active_dock if self.active_dock and self.active_dock.isFloating() else next(
            (item for item in reversed(self.docks) if item.isFloating()), None)
        if dock:
            self.adopt(dock)

    def arrange(self, dock, placement):
        if dock is None or dock not in self.docks:
            return
        other = self._docked_anchor(excluding=dock)
        self._hide_drop_target()
        dock.setFloating(False)
        if other is None:
            self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        elif placement == 'tabs':
            self.tabifyDockWidget(other, dock)
        else:
            # Qt treats splitDockWidget's first argument as a whole tab group.
            # Remove both anchors to dissolve that group before splitting them.
            self.removeDockWidget(dock)
            self.removeDockWidget(other)
            first, second = (dock, other) if placement == 'left' else (other, dock)
            self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, first)
            self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, second)
            first.show()
            second.show()
            self.splitDockWidget(first, second, qt.Qt.Orientation.Horizontal)
        dock.show()
        dock.raise_()
        self._activate(dock)

    def adopt(self, dock):
        """Transfer the actual view, retaining history, controllers and running jobs."""
        if self._closing:
            return
        source = dock.workspace
        if source is not self:
            source.remove_view(dock)
            dock.workspace = self
            dock.setParent(self)
            self.docks.append(dock)
        previous = self._docked_anchor(excluding=dock)
        self._hide_drop_target()
        self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        dock.setFloating(False)
        if previous and previous is not dock:
            self.tabifyDockWidget(previous, dock)
        dock.show()
        dock.raise_()
        self._activate(dock)

    def close_active(self):
        if self.active_dock:
            self.active_dock.close()

    def _retry_view_close(self, dock):
        if dock not in self.docks:
            return
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
        self._update_drop_target()

    def prepare_close(self):
        self._closing = True
        self._update_drop_target()
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
