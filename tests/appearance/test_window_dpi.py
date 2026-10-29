"""Native Windows DPI sequences preserve real Qt logical window dimensions."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import ctypes
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.pyside.window_dpi import (
    WindowDpiScaleFixer, install_window_dpi_scale_fixer, WM_DPICHANGED,
    WM_GETDPISCALEDSIZE, WM_SIZING, WM_ENTERSIZEMOVE, WM_EXITSIZEMOVE,
)


class WindowDpiTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.helper = WindowDpiScaleFixer(self.app)
        self.addCleanup(self.helper.deleteLater)
        self.addCleanup(self.helper.close)
        self.window = qt.QWidget()
        self.window.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.window.resize(360, 240)
        self.window.show()
        self.app.processEvents()

    def native(self, message, dpi=192):
        native = wintypes.MSG()
        native.hWnd = int(self.window.winId())
        native.message = message
        native.wParam = dpi | (dpi << 16)
        self.assertEqual(self.helper.native_filter.nativeEventFilter(
            b'windows_generic_MSG', ctypes.addressof(native)), (False, 0))

    def settled(self):
        self.wait_until(lambda: self.window not in self.helper.pending,
                        message='DPI transition did not settle')

    def test_crossing_to_200_percent_repairs_either_or_both_dimensions(self):
        for size in (qt.QSize(720, 240), qt.QSize(360, 480), qt.QSize(720, 480)):
            self.native(WM_ENTERSIZEMOVE)
            self.native(WM_GETDPISCALEDSIZE)
            self.native(WM_DPICHANGED)
            self.window.resize(size)  # Simulate native size drift after Qt updates DPI.
            self.native(WM_EXITSIZEMOVE)
            self.settled()
            self.assertEqual(self.window.size(), qt.QSize(360, 240))

    def test_crossing_back_to_100_percent_keeps_logical_size(self):
        self.native(WM_GETDPISCALEDSIZE, 96)
        self.native(WM_DPICHANGED, 96)
        self.window.resize(180, 120)
        self.settled()
        self.assertEqual(self.window.size(), qt.QSize(360, 240))

    def test_rapid_crossings_do_not_capture_a_transient_scaled_size(self):
        self.native(WM_GETDPISCALEDSIZE)
        self.native(WM_DPICHANGED)
        self.window.resize(720, 480)
        self.native(WM_GETDPISCALEDSIZE, 96)
        self.native(WM_DPICHANGED, 96)
        self.window.resize(180, 120)
        self.settled()
        self.assertEqual(self.window.size(), qt.QSize(360, 240))

    def test_real_user_resize_cancels_pending_dpi_repair(self):
        self.native(WM_DPICHANGED)
        token = self.helper.pending[self.window][1]
        self.native(WM_SIZING)
        self.window.resize(480, 300)
        self.helper._restore(self.window, token, finish=True)
        self.app.processEvents()
        self.assertNotIn(self.window, self.helper.pending)
        self.assertEqual(self.window.size(), qt.QSize(480, 300))

    def test_reentrant_crossing_during_repair_keeps_new_transition(self):
        self.native(WM_DPICHANGED)
        token = self.helper.pending[self.window][1]
        self.window.resize(720, 480)
        resize = self.window.resize
        def crossing(size):
            self.native(WM_DPICHANGED, 96)
            resize(size)
        with patch.object(self.window, 'resize', side_effect=crossing):
            self.helper._restore(self.window, token, finish=True)
        self.assertIn(self.window, self.helper.pending)
        self.assertIsNot(self.helper.pending[self.window][1], token)
        self.settled()
        self.assertEqual(self.window.size(), qt.QSize(360, 240))

    def test_programmatic_resize_at_screen_crossing_uses_requested_size(self):
        self.window.resize(480, 300)
        # Qt's setGeometry path does not receive WM_GETDPISCALEDSIZE.
        self.native(WM_DPICHANGED)
        self.window.resize(960, 600)
        self.settled()
        self.assertEqual(self.window.size(), qt.QSize(480, 300))

    def test_unchanged_logical_size_needs_no_resize(self):
        self.native(WM_DPICHANGED)
        with patch.object(self.window, 'resize', wraps=self.window.resize) as resize:
            self.settled()
        resize.assert_not_called()

    def test_maximized_fullscreen_and_popups_keep_native_geometry(self):
        for state in (qt.Qt.WindowState.WindowMaximized, qt.Qt.WindowState.WindowFullScreen):
            self.window.setWindowState(state)
            self.native(WM_DPICHANGED)
            self.assertNotIn(self.window, self.helper.pending)
        self.window.setWindowState(qt.Qt.WindowState.WindowNoState)
        self.window.setWindowFlags(qt.Qt.WindowType.Popup)
        self.window.show()
        self.native(WM_DPICHANGED)
        self.assertNotIn(self.window, self.helper.pending)

    def test_window_deletion_cancels_queued_repairs(self):
        self.native(WM_DPICHANGED)
        self.window.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.app.processEvents()
        from shiboken6 import isValid
        self.assertFalse(isValid(self.window))

    def test_installation_is_windows_only_and_idempotent(self):
        with patch('commonUtils.ui.pyside.window_dpi.sys', SimpleNamespace(platform='darwin')):
            self.assertIsNone(install_window_dpi_scale_fixer(self.app))
        with patch('commonUtils.ui.pyside.window_dpi.sys', SimpleNamespace(platform='win32')):
            installed = install_window_dpi_scale_fixer(self.app)
            self.addCleanup(installed.deleteLater)
            self.addCleanup(installed.close)
            self.assertIs(install_window_dpi_scale_fixer(self.app), installed)
        self.assertTrue(issubclass(qt.WindowDpiScaleFixer, qt.QObject))
