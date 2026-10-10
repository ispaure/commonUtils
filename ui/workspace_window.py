"""A detached container owns tabs and closes them with its native window."""
from . import pyside as qt


class WorkspaceWindow(qt.QMainWindow):
    def __init__(self, main, *, allow_new_tabs=None, policy=None):
        super().__init__(main.window())
        from .workspace import Workspace
        self.setWindowFlag(qt.Qt.WindowType.Window, True)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self._native_drag = None
        self._title_press = None
        self._native_drag_blocked = False
        self._last_geometry = self.geometry()
        self.workspace = Workspace(main.factory, self, allow_new_tabs=main.allow_new_tabs if allow_new_tabs is None else allow_new_tabs,
                                   dock_group=main.dock_group, keep_one_tab=main.keep_one_tab,
                                   policy=policy or main.policy, main_workspace=main,
                                   new_view=main.new_view, setup_container=main.setup_container)
        self.setCentralWidget(self.workspace)
        self.workspace.close_action.setEnabled(main.close_action.isEnabled())
        from .workspace_cocoa import register_title_bar
        register_title_bar(self)
        self.installEventFilter(self)
        self.resize(1000, 700)
        self.workspace.active_changed.connect(self.update_title)
        self.workspace.tabs_changed.connect(self.update_title)
        if main.setup_container is not None:
            main.setup_container(self.workspace)

    def dock_to_main(self):
        main = self.workspace.main_workspace
        restore = main.reveal_for_drop(main.window().frameGeometry().center())
        for dock in tuple(self.workspace.docks):
            if not main.adopt(dock):
                if callable(restore):
                    restore()
                return False
        return True

    def title_bar_menu(self, point):
        menu = qt.QMenu(self)
        menu.addAction('Dock back to main window', self.dock_to_main)
        menu.exec(point)
        menu.deleteLater()

    def eventFilter(self, watched, event):
        if watched is self:
            kind = event.type()
            if kind == qt.QEvent.Type.NonClientAreaMouseButtonPress:
                if event.button() == qt.Qt.MouseButton.RightButton:
                    self.title_bar_menu(event.globalPosition().toPoint())
                    return True
                if event.button() == qt.Qt.MouseButton.LeftButton:
                    self._native_drag_blocked = False
                    self._last_geometry = self.geometry()
            if kind == qt.QEvent.Type.NonClientAreaMouseButtonRelease:
                self._native_drag_blocked = False
            if kind == qt.QEvent.Type.ContextMenu:
                self.title_bar_menu(event.globalPos())
                return True
        return super().eventFilter(watched, event)

    def moveEvent(self, event):
        super().moveEvent(event)
        # Cocoa does not consistently emit non-client mouse events. Window move
        # events plus the live mouse state also cover native macOS title bars.
        from .workspace_cocoa import left_button_pressed
        if (self.isVisible() and self._native_drag is None and not self._native_drag_blocked
                and left_button_pressed()
                and self.workspace.docks):
            from .workspace_drag import NativeWindowDrag
            self._native_drag = NativeWindowDrag(self, self._last_geometry)
            self._native_drag.move(qt.QCursor.pos())
        if self._native_drag is None:
            self._last_geometry = self.geometry()

    def update_title(self, *args):
        dock = self.workspace.active_dock
        title = dock.windowTitle() if dock else ''
        self.setWindowTitle(self.workspace.policy.detached_title.format(title=title))

    def closeEvent(self, event):
        if self._native_drag is not None:
            self._native_drag.finish(qt.QCursor.pos(), cancel=True)
        main = self.workspace.main_workspace
        if not main._closing:
            # Closing the whole window may close its last browser tab too.
            # Keep each view's close handler authoritative for vetoes and workers.
            keep_one_tab = self.workspace.keep_one_tab
            self.workspace.keep_one_tab = False
            try:
                for dock in tuple(self.workspace.docks):
                    dock.close()
            finally:
                self.workspace.keep_one_tab = keep_one_tab
        if self.workspace.docks or self.workspace._retiring:
            event.ignore()
            return
        event.accept()
