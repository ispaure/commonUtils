"""Preserve normal Windows QWidget logical sizes across native DPI transitions."""
from ctypes import wintypes
import sys
from weakref import WeakKeyDictionary, ref

from shiboken6 import isValid
from . import _api as qt

WM_SIZING = 0x0214
WM_ENTERSIZEMOVE = 0x0231
WM_EXITSIZEMOVE = 0x0232
WM_DPICHANGED = 0x02E0
WM_GETDPISCALEDSIZE = 0x02E4


class _NativeDpiEvents(qt.QAbstractNativeEventFilter):
    def __init__(self, owner):
        super().__init__()
        self.owner = ref(owner)

    def nativeEventFilter(self, event_type, message):
        kind = event_type.encode() if isinstance(event_type, str) else bytes(event_type)
        owner = self.owner()
        if (kind != b'windows_generic_MSG' or not message or owner is None
                or not isValid(owner) or owner.closed):
            return False, 0
        native = wintypes.MSG.from_address(int(message))
        if native.message in (WM_SIZING, WM_ENTERSIZEMOVE, WM_EXITSIZEMOVE,
                              WM_DPICHANGED, WM_GETDPISCALEDSIZE):
            window = qt.QWidget.find(int(native.hWnd or 0))
            if window is not None:
                owner.native_message(window, native.message)
        # Qt still owns DPI awareness, frame margins, screen selection and placement.
        return False, 0


class WindowDpiScaleFixer(qt.QObject):
    """Observe native DPI changes and repair only logical client-size drift.

    Retain one instance per QApplication. The installer enables it on Windows;
    direct construction also supports synthetic native-event tests on other hosts.
    """
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.closed = False
        self.before_scale = WeakKeyDictionary()
        self.pending = WeakKeyDictionary()
        self.native_filter = _NativeDpiEvents(self)
        app.installEventFilter(self)
        app.installNativeEventFilter(self.native_filter)

    @staticmethod
    def eligible(window):
        return (isValid(window) and window.isWindow() and window.isVisible()
                and window.windowType() in (qt.Qt.WindowType.Window, qt.Qt.WindowType.Dialog, qt.Qt.WindowType.Tool)
                and not window.isMaximized() and not window.isMinimized() and not window.isFullScreen())

    def close(self):
        if self.closed:
            return
        self.closed = True
        if isValid(self.app):
            self.app.removeEventFilter(self)
            self.app.removeNativeEventFilter(self.native_filter)
        self.pending.clear()
        self.before_scale.clear()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind not in (qt.QEvent.Type.Hide, qt.QEvent.Type.WindowStateChange, qt.QEvent.Type.Resize):
            return False
        if isinstance(watched, qt.QWidget) and isValid(watched) and watched.isWindow():
            if kind in (qt.QEvent.Type.Hide, qt.QEvent.Type.WindowStateChange):
                self.pending.pop(watched, None)
                self.before_scale.pop(watched, None)
            elif kind == qt.QEvent.Type.Resize and watched not in self.pending:
                # An ordinary resize invalidates any unused pre-transition sample.
                self.before_scale.pop(watched, None)
        return False

    def native_message(self, window, message):
        if self.closed or not self.eligible(window):
            self.pending.pop(window, None)
            self.before_scale.pop(window, None)
            return
        if message in (WM_ENTERSIZEMOVE, WM_SIZING):
            # A real resize gesture takes precedence over a previous DPI repair.
            self.pending.pop(window, None)
            self.before_scale.pop(window, None)
        elif message == WM_GETDPISCALEDSIZE:
            # Interactive monitor crossing supplies this before Qt changes DPI.
            if window not in self.pending:
                self.before_scale[window] = qt.QSize(window.size())
        elif message == WM_DPICHANGED:
            existing = self.pending.get(window)
            size = existing[0] if existing else self.before_scale.pop(window, qt.QSize(window.size()))
            token = object()
            self.pending[window] = (qt.QSize(size), token)
            self._queue_restore(window, token)
        elif message == WM_EXITSIZEMOVE:
            self.before_scale.pop(window, None)
            if window in self.pending:
                self._queue_restore(window, self.pending[window][1])

    def _queue_restore(self, window, token):
        # Run after Qt handles WM_DPICHANGED, then once more after native geometry
        # notifications settle. QObject context cancels work for deleted windows.
        qt.QTimer.singleShot(0, window, lambda: self._restore(window, token))
        qt.QTimer.singleShot(50, window, lambda: self._restore(window, token, finish=True))

    def _restore(self, window, token, *, finish=False):
        if not isValid(self) or self.closed or not self.eligible(window):
            return
        transition = self.pending.get(window)
        if transition is None or transition[1] is not token:
            return
        size = transition[0]
        if window.size() != size:
            window.resize(size)
        # Resizing can itself trigger another screen crossing. Do not retire a
        # newer transition created reentrantly by Windows during that resize.
        current = self.pending.get(window)
        if finish and current is not None and current[1] is token:
            self.pending.pop(window, None)


def install_window_dpi_scale_fixer(app):
    """Install the Windows-only policy once; other platforms use Qt directly."""
    if sys.platform != 'win32':
        return None
    helper = getattr(app, '_commonutils_window_dpi_fixer', None)
    if helper is None or not isValid(helper) or helper.closed:
        helper = WindowDpiScaleFixer(app)
        app._commonutils_window_dpi_fixer = helper
    return helper
