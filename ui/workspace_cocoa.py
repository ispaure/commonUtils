"""Small Cocoa bridge for native title bars, which bypass QWidget mouse events.

Qt exposes NSEvent through QAbstractNativeEventFilter:
https://doc.qt.io/qt-6/qabstractnativeeventfilter.html
Only scalar Objective-C messages are used; Qt still owns windows and dragging.
"""
import ctypes
import sys
from weakref import WeakSet
from PySide6.QtCore import QAbstractNativeEventFilter
from shiboken6 import isValid
from . import pyside as qt

_bridge = None


class CocoaTitleBars(QAbstractNativeEventFilter):
    def __init__(self):
        super().__init__()
        self.windows = WeakSet()
        objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.objc_getClass.restype = ctypes.c_void_p
        self.selectors = {name: objc.sel_registerName(name.encode()) for name in
                          ('type', 'window', 'pressedMouseButtons')}
        address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
        self.pointer = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(address)
        self.integer = ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)(address)
        self.event_class = objc.objc_getClass(b'NSEvent')

    def left_pressed(self):
        return bool(self.integer(self.event_class, self.selectors['pressedMouseButtons']) & 1)

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) != b'mac_generic_NSEvent':
            return False, 0
        event = int(message)
        kind = self.integer(event, self.selectors['type'])
        if kind not in (1, 2, 3, 6):  # left down/up, right down, left drag
            return False, 0
        native_window = self.pointer(event, self.selectors['window'])
        point = qt.QCursor.pos()
        for window in tuple(self.windows):
            if not isValid(window) or not window.isVisible():
                continue
            if self.pointer(int(window.winId()), self.selectors['window']) != native_window:
                continue
            if kind == 2:
                window._title_press = None
                window._native_drag_blocked = False
                if window._native_drag is not None:
                    window._native_drag.finish(point)
            elif (kind == 6 and window._title_press is not None and window._native_drag is None
                  and not window._native_drag_blocked):
                if (point - window._title_press).manhattanLength() >= qt.QApplication.startDragDistance():
                    from .workspace_drag import NativeWindowDrag
                    window._native_drag = NativeWindowDrag(window, window._last_geometry)
                    window._native_drag.move(point)
            title_bar = window.frameGeometry().contains(point) and not window.geometry().contains(point)
            if title_bar and kind == 1:
                window._native_drag_blocked = False
                window._last_geometry = window.geometry()
                window._title_press = point
            elif title_bar and kind == 3:
                # Leave Cocoa's event dispatch before running a Qt popup loop.
                qt.QTimer.singleShot(0, window, lambda owner=window, pos=point: owner.title_bar_menu(pos))
                return True, 0
        return False, 0


def register_title_bar(window):
    global _bridge
    if sys.platform != 'darwin' or qt.QApplication.platformName() != 'cocoa':
        return
    if _bridge is None:
        _bridge = CocoaTitleBars()
        qt.QApplication.instance().installNativeEventFilter(_bridge)
    _bridge.windows.add(window)


def left_button_pressed():
    return _bridge.left_pressed() if _bridge is not None else bool(
        qt.QApplication.mouseButtons() & qt.Qt.MouseButton.LeftButton)
