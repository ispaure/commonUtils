"""Repair missing Cocoa window entry through Qt's normal widget dispatch."""

from shiboken6 import isValid
from weakref import ref
from . import _api as qt


class PointerEntryRecovery(qt.QObject):
    """Seed entry after show/activation, or before an otherwise orphaned move.

    A missing top-level Enter leaves QApplication's last mouse receiver unset.
    Moving between child widgets then need not generate their Enter/Leave events.
    Sending Enter to the QWindow lets Qt establish the complete widget chain.
    """

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._delivered_position = None
        self._hover_window = None
        self.recovered_moves = 0
        self.timer = qt.QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll_pointer)
        app.applicationStateChanged.connect(self._application_state_changed)
        self._application_state_changed(app.applicationState())
        app.installEventFilter(self)

    def eligible(self, window, *, require_missing_entry=True):
        modal = self.app.activeModalWidget()
        return (isValid(window) and window.isVisible() and window.isActiveWindow()
                and not window.isMinimized() and (not require_missing_entry or not window.underMouse())
                and self.app.applicationState() == qt.Qt.ApplicationState.ApplicationActive
                and self.app.activePopupWidget() is None
                and (modal is None or modal is window)
                and qt.QWidget.mouseGrabber() is None
                and self.app.mouseButtons() == qt.Qt.MouseButton.NoButton)

    def restore(self, window, global_pos, *, move=False):
        if not self.eligible(window, require_missing_entry=not move):
            return
        hit = self.app.widgetAt(global_pos.toPoint())
        if hit is None or hit.window() is not window:
            return
        handle = window.windowHandle()
        if handle is None:
            return
        local = qt.QPointF(window.mapFromGlobal(global_pos.toPoint()))
        if not window.underMouse() or not hit.underMouse():
            # The window may have entered while its children still lack entry
            # state. Reset Qt's receiver chain before seeding it in that case.
            if window.underMouse():
                self.app.sendEvent(handle, qt.QEvent(qt.QEvent.Type.Leave))
            self.app.sendEvent(handle, qt.QEnterEvent(local, local, global_pos))
        if move and isValid(window) and isValid(handle):
            # Item views also need a move to locate the hovered row. No button,
            # focus, activation or cursor-position change is synthesized.
            self.app.sendEvent(handle, qt.QMouseEvent(
                qt.QEvent.Type.MouseMove, local, global_pos,
                qt.Qt.MouseButton.NoButton, qt.Qt.MouseButton.NoButton,
                self.app.keyboardModifiers()))

    def _application_state_changed(self, state):
        self._delivered_position = None
        if state == qt.Qt.ApplicationState.ApplicationActive:
            self.timer.start()
        else:
            self.timer.stop()

    def poll_pointer(self):
        """Fill gaps in native delivery; healthy mouse moves do no extra work."""
        if (self.app.applicationState() != qt.Qt.ApplicationState.ApplicationActive
                or self.app.mouseButtons() != qt.Qt.MouseButton.NoButton
                or qt.QWidget.mouseGrabber() is not None
                or self.app.activePopupWidget() is not None):
            return
        position = qt.QPointF(qt.QCursor.pos())
        hit = self.app.widgetAt(position.toPoint())
        if position == self._delivered_position and (hit is None or hit.underMouse() or not hit.isEnabled()):
            return
        window = hit.window() if hit is not None else None
        modal = self.app.activeModalWidget()
        if modal is not None and window is not modal:
            return
        previous = self._hover_window() if self._hover_window is not None else None
        if previous is not None and isValid(previous) and previous is not window:
            handle = previous.windowHandle()
            if handle is not None:
                self.app.sendEvent(handle, qt.QEvent(qt.QEvent.Type.Leave))
            self._hover_window = None
        if window is not None and self.eligible(window, require_missing_entry=False):
            self.restore(window, position, move=True)
            self.recovered_moves += 1
        self._delivered_position = position

    def _after_show(self, window):
        if isValid(self):
            self.restore(window, qt.QPointF(qt.QCursor.pos()), move=True)

    def eventFilter(self, watched, event):
        kind = event.type()
        if (kind in (qt.QEvent.Type.Show, qt.QEvent.Type.WindowActivate)
                and isinstance(watched, qt.QWidget) and watched.isWindow()):
            # Activation and native mapping must finish first. The window context
            # cancels the callback if it is destroyed during startup/closing.
            qt.QTimer.singleShot(0, watched, lambda: self._after_show(watched))
        elif (kind == qt.QEvent.Type.MouseMove and isinstance(watched, qt.QWindow)
              and event.buttons() == qt.Qt.MouseButton.NoButton):
            window = qt.QWidget.find(int(watched.winId()))
            if window is not None and window.isWindow():
                self._delivered_position = event.globalPosition()
                self._hover_window = ref(window)
                self.restore(window, event.globalPosition())
        return False


def install_pointer_entry_recovery(app):
    """Install once for Cocoa; other Qt backends retain their native behavior."""
    if app.platformName() != 'cocoa':
        return None
    helper = getattr(app, '_commonutils_pointer_entry', None)
    if helper is None or not isValid(helper):
        helper = PointerEntryRecovery(app)
        app._commonutils_pointer_entry = helper
    return helper
