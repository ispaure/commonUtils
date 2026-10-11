"""Shared macOS menu placement, including live changes to ui/settings.ini."""
import sys

from . import pyside as qt
from ..configuration.settings import get_setting


def native_menus_enabled():
    """Windows/Linux always use in-window menus; macOS defaults to native."""
    return sys.platform == 'darwin' and get_setting('Menus', 'macos_native_bool', True)


class MenuPolicy(qt.QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.native = None
        self.pending = False
        self.refresh()
        app.installEventFilter(self)
        self.timer = qt.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def eventFilter(self, watched, event):
        # Workspace publication deliberately sends ParentChange to rebind its
        # native bar. Feeding that event back into every context creates an
        # endless publication loop and interrupts AppKit menu tracking.
        if (isinstance(watched, qt.QMenuBar)
                and getattr(watched.parent(), '_workspace_menu_context', None) is None
                and event.type() in (
                qt.QEvent.Type.Show, qt.QEvent.Type.Polish, qt.QEvent.Type.ParentChange)):
            if not self.pending:
                self.pending = True
                qt.QTimer.singleShot(0, self, self.apply)
        return False

    def refresh(self):
        native = native_menus_enabled()
        if native != self.native:
            self.native = native
            qt.QCoreApplication.setAttribute(qt.Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, not native)
            self.apply(restore_sources=True)

    def apply(self, *, restore_sources=False):
        self.pending = False
        widgets = self.app.allWidgets()
        for bar in widgets:
            if not isinstance(bar, qt.QMenuBar):
                continue
            source = getattr(bar, '_workspace_menu_source', False)
            if getattr(bar.parent(), '_workspace_menu_context', None) is not None:
                continue
            bar.setNativeMenuBar(self.native and not source)
            if restore_sources and source and not self.native:
                host = bar.window()
                workspace = getattr(host, 'workspace', None)
                published = (getattr(host, 'workspace_publish_menus', False)
                             or getattr(workspace, 'is_detached', False))
                bar.setVisible(bool(bar.actions()) and not published)
        # Route after restoring sources: detached windows still own their menus.
        for widget in widgets:
            context = getattr(widget, '_workspace_menu_context', None)
            if context is not None:
                context.schedule()


def install_menu_policy(app=None):
    """Install once per QApplication; no import-time application side effects."""
    app = app or qt.QApplication.instance()
    if app is None:
        raise RuntimeError('Create QApplication before installing menu policy')
    controller = getattr(app, '_commonutils_menu_policy', None)
    if controller is None:
        controller = app._commonutils_menu_policy = MenuPolicy(app)
    return controller
