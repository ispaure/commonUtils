"""Native window-state synchronization and shared reader layout boundaries."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.reader_chrome import ReaderFullscreen, ReaderLabel, reader_button


class ReaderChromeTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def window(self):
        window = qt.QMainWindow()
        self.addCleanup(window.deleteLater)
        action = qt.QAction('Full screen', window)
        action.setCheckable(True)
        controller = ReaderFullscreen(window, action)
        window.show()
        self.app.processEvents()
        return window, action, controller

    def test_fullscreen_toggle_and_native_exit_update_action_and_button(self):
        window, action, controller = self.window()
        button = reader_button(window, 'Full screen', action=action, icon='fullscreen')
        controller.toggle()
        self.assertTrue(window.isFullScreen())
        self.assertTrue(action.isChecked())
        self.assertEqual(button.accessibleName(), 'Exit full screen')
        window.showNormal()  # Native title-bar/OS exit, outside our toggle action.
        self.app.processEvents()
        self.assertFalse(action.isChecked())
        self.assertEqual(button.accessibleName(), 'Full screen')

    def test_maximized_window_is_restored_on_exit(self):
        window, action, controller = self.window()
        window.showMaximized()
        controller.toggle()
        controller.leave()
        self.assertTrue(window.isMaximized())
        self.assertFalse(window.isFullScreen())
        self.assertFalse(action.isChecked())

    def test_native_fullscreen_entry_also_remembers_maximized_state(self):
        window, action, controller = self.window()
        window.showMaximized()
        window.showFullScreen()
        self.app.processEvents()
        controller.leave()
        self.assertTrue(window.isMaximized())

    def test_reader_title_remains_single_line_and_retains_full_accessible_text(self):
        title = 'A very long title ' * 40
        label = ReaderLabel(title)
        self.addCleanup(label.deleteLater)
        label.resize(180, 32)
        label.show()
        self.app.processEvents()
        label.grab()  # Elided painting must not overwrite the source label text.
        self.assertEqual(label.text(), title)
        self.assertEqual(label.toolTip(), title)
        self.assertFalse(label.wordWrap())
        self.assertLess(label.minimumSizeHint().width(), label.fontMetrics().horizontalAdvance(title))
