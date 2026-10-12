"""Route active view menus to native macOS bars and detached desktop headers."""
import sys
from .. import pyside as qt
from shiboken6 import isValid
from ..menu_policy import install_menu_policy, native_menus_enabled


class _MenuContext(qt.QObject):
    """Resync after Qt settles focus/reparenting, without stealing focus."""
    def __init__(self, container):
        super().__init__(container)
        self.container = container
        self.document = None
        self.source = None
        self.pending = False
        self.published_actions = None
        self.redraw_pending = False
        container.installEventFilter(self)
        qt.QApplication.instance().focusChanged.connect(self._focus_changed)
        qt.QApplication.instance().focusWindowChanged.connect(self._focus_window_changed)

    def set_document(self, document):
        self.document = document
        source = document.menuBar() if isinstance(document, qt.QMainWindow) and isValid(document) else None
        if source is not self.source:
            if self.source is not None and isValid(self.source):
                self.source.removeEventFilter(self)
            self.source = source
            if source is not None:
                source.installEventFilter(self)

    def schedule(self):
        if not self.pending:
            self.pending = True
            qt.QTimer.singleShot(0, self, self.refresh)

    def _focus_changed(self, old, current):
        if current is not None and current.window() is self.container:
            self.schedule()

    def _focus_window_changed(self, window):
        # Closing a native popup can return focus to the host without changing
        # its focused QWidget or emitting another WindowActivate. Cocoa skips
        # menu publication while that popup is the focus window.
        if window is not None and window is self.container.windowHandle():
            self.redraw_pending = True
            self.schedule()

    def eventFilter(self, watched, event):
        if ((watched is self.container and event.type() in
             (qt.QEvent.Type.Show, qt.QEvent.Type.WindowActivate)) or
            (watched is self.source and event.type() in
             (qt.QEvent.Type.ActionAdded, qt.QEvent.Type.ActionRemoved, qt.QEvent.Type.ActionChanged))):
            self.redraw_pending = True
            self.schedule()
        return super().eventFilter(watched, event)

    def refresh(self):
        self.pending = False
        if not isValid(self.container):
            return
        provider = getattr(self.container, 'workspace_menu_document', None)
        document = provider() if callable(provider) else self.document
        self.set_document(document)
        _apply_menus(self.container, document)
        bar = self.container.menuBar()
        if sys.platform == 'darwin' and native_menus_enabled() and qt.QApplication.platformName() == 'cocoa':
            # QMenuBar handles ParentChange by rebinding its platform bar to the
            # current top-level QWindow. Embedded readers can create native
            # handles before adoption; refresh that binding after focus settles.
            qt.QCoreApplication.sendEvent(bar, qt.QEvent(qt.QEvent.Type.ParentChange))
            # AppKit can expose the correct NSMenu while still drawing the old
            # bar. Invalidate its display after publication, only for the focused
            # host and only when its context changes or returns to the foreground.
            actions = tuple(bar.actions())
            if qt.QApplication.focusWindow() is self.container.windowHandle():
                if self.redraw_pending or actions != self.published_actions:
                    from .workspace_cocoa import redraw_menu_bar
                    redraw_menu_bar()
                self.published_actions = actions
                self.redraw_pending = False


def sync_native_menus(container, document=None):
    if not isinstance(container, qt.QMainWindow):
        return
    install_menu_policy()
    provider = getattr(container, 'workspace_menu_document', None)
    if callable(provider):
        document = provider()
    context = getattr(container, '_workspace_menu_context', None)
    if context is None:
        context = container._workspace_menu_context = _MenuContext(container)
    context.set_document(document)
    _apply_menus(container, document)
    context.schedule()


def _apply_menus(container, document=None):
    if not isinstance(container, qt.QMainWindow):
        return
    native = native_menus_enabled()
    # Attached views keep their in-page menus on Windows/Linux. Detached
    # containers expose the active document's menus in their own header.
    if (not native and not getattr(container, 'workspace_publish_menus', False)
            and not getattr(getattr(container, 'workspace', None), 'is_detached', False)):
        bar = container.menuBar()
        if hasattr(container, '_workspace_base_menus'):
            actions = [a for a in container._workspace_base_menus if isValid(a)]
            if bar.actions() != actions:
                for action in bar.actions():
                    bar.removeAction(action)
                for action in actions:
                    bar.addAction(action)
        bar.setNativeMenuBar(False)
        bar.setVisible(bool(bar.actions()))
        if isinstance(document, qt.QMainWindow) and isValid(document):
            document.menuBar()._workspace_menu_source = True
            document.menuBar().setNativeMenuBar(False)
            document.menuBar().show()
        return
    bar = container.menuBar()
    if not hasattr(container, '_workspace_base_menus'):
        container._workspace_base_menus = list(bar.actions())
    actions = container._workspace_base_menus
    if isinstance(document, qt.QMainWindow) and isValid(document):
        source = document.menuBar()
        source._workspace_menu_source = True
        source.setNativeMenuBar(False)
        source.hide()
        # PySide can transfer a QMenu wrapper's ownership to menuAction().
        # Retain these wrappers with the original bar, across tab switches and
        # container destruction, so accessing action.menu() cannot delete it.
        source._workspace_menu_actions = source.actions()
        actions = source._workspace_menu_actions
    extras = getattr(container, 'workspace_menu_actions', ())
    actions = list(dict.fromkeys(action for action in [*extras, *actions] if isValid(action)))
    changed = bar.actions() != actions
    native_changed = bar.isNativeMenuBar() != native
    if native_changed or changed:
        if native:
            bar.setNativeMenuBar(False)
        for action in bar.actions():
            bar.removeAction(action)
        bar.setNativeMenuBar(native)
        for action in actions:
            bar.addAction(action)
    bar.setVisible(bool(bar.actions()))
