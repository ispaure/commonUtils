"""Recover missing top-level entry without changing focus or mouse gestures."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.pyside.pointer_entry import PointerEntryRecovery, install_pointer_entry_recovery


class PointerEntryTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.window = qt.QWidget()
        layout = qt.QVBoxLayout(self.window)
        self.button = qt.QPushButton('Open')
        self.button.setStyleSheet('QPushButton { background: #ffffff; border: none; } '
                                 'QPushButton:hover { background: #ccddff; }')
        layout.addWidget(self.button)
        self.list = qt.QListWidget()
        self.list.setMouseTracking(True)
        self.list.addItems(['First', 'Second'])
        self.list.setStyleSheet('QListWidget::item:hover { background: #ccddff; }')
        layout.addWidget(self.list)
        self.window.resize(320, 240)
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()
        self.handle = self.window.windowHandle()
        self.helper = PointerEntryRecovery(self.app)
        self.addCleanup(self.helper.deleteLater)
        self.addCleanup(self.app.removeEventFilter, self.helper)

    def leave(self):
        self.app.sendEvent(self.handle, qt.QEvent(qt.QEvent.Type.Leave))
        self.assertFalse(self.window.underMouse())

    def move(self, widget, pos=None):
        pos = pos or widget.rect().center()
        global_pos = widget.mapToGlobal(pos)
        local = self.window.mapFromGlobal(global_pos)
        self.app.sendEvent(self.handle, qt.QMouseEvent(
            qt.QEvent.Type.MouseMove, qt.QPointF(local), qt.QPointF(global_pos),
            qt.Qt.MouseButton.NoButton, qt.Qt.MouseButton.NoButton,
            qt.Qt.KeyboardModifier.NoModifier))

    def test_missing_entry_recovers_button_and_subsequent_pointer_transitions(self):
        self.leave()  # Model a lost native Enter before the first MouseMove.
        self.move(self.button)
        self.assertTrue(self.button.underMouse())
        self.assertEqual(self.button.grab().toImage().pixelColor(5, 5), qt.QColor('#ccddff'))
        self.move(self.list.viewport(), qt.QPoint(20, 10))
        self.assertFalse(self.button.underMouse())
        self.assertTrue(self.list.viewport().underMouse())
        self.assertEqual(self.list.viewport().grab().toImage().pixelColor(200, 5), qt.QColor('#ccddff'))

    def test_recovery_preserves_keyboard_focus_and_does_not_click(self):
        self.list.setFocus()
        clicked = []
        self.button.clicked.connect(lambda: clicked.append(True))
        self.leave()
        self.move(self.button)
        self.assertTrue(self.button.underMouse())
        self.assertIs(self.app.focusWidget(), self.list)
        self.assertEqual(clicked, [])

    def test_activation_seeds_hover_under_a_stationary_pointer(self):
        self.leave()
        position = self.button.mapToGlobal(self.button.rect().center())
        with patch.object(qt.QCursor, 'pos', return_value=position):
            self.app.sendEvent(self.window, qt.QEvent(qt.QEvent.Type.WindowActivate))
            self.assertFalse(self.button.underMouse())  # Wait for native activation to finish.
            self.app.processEvents()
        self.assertTrue(self.button.underMouse())

    def test_healthy_hover_is_not_reentered_on_every_move(self):
        self.leave()
        self.move(self.button)
        with patch.object(self.app, 'sendEvent', wraps=self.app.sendEvent) as send:
            self.move(self.button, qt.QPoint(20, 10))
        self.assertEqual(len(send.call_args_list), 1)  # Only the original move.

    def test_drag_popup_modal_grab_and_inactive_app_are_left_to_qt(self):
        for method, value in (
            ('mouseButtons', qt.Qt.MouseButton.LeftButton),
            ('activePopupWidget', self.button),
            ('activeModalWidget', self.button),
            ('applicationState', qt.Qt.ApplicationState.ApplicationInactive),
        ):
            with self.subTest(guard=method):
                self.leave()
                with patch.object(self.app, method, return_value=value):
                    self.move(self.button)
                self.assertFalse(self.button.underMouse())
        self.leave()
        with patch.object(qt.QWidget, 'mouseGrabber', return_value=self.button):
            self.move(self.button)
        self.assertFalse(self.button.underMouse())

    def test_deferred_recovery_rechecks_visibility_and_hit_window(self):
        self.leave()
        position = self.button.mapToGlobal(self.button.rect().center())
        with patch.object(qt.QCursor, 'pos', return_value=position):
            self.app.sendEvent(self.window, qt.QEvent(qt.QEvent.Type.WindowActivate))
            with patch.object(self.app, 'widgetAt', return_value=None):
                self.app.processEvents()
        self.assertFalse(self.button.underMouse())
        self.window.hide()
        self.helper.restore(self.window, qt.QPointF(position), move=True)
        self.assertFalse(self.button.underMouse())

    def test_installer_is_cocoa_only_and_idempotent(self):
        previous = getattr(self.app, '_commonutils_pointer_entry', None)
        with patch.object(self.app, 'platformName', return_value='offscreen'):
            self.assertIsNone(install_pointer_entry_recovery(self.app))
        with patch.object(self.app, 'platformName', return_value='cocoa'):
            installed = install_pointer_entry_recovery(self.app)
            self.assertIs(install_pointer_entry_recovery(self.app), installed)
        if installed is not previous:
            self.app.removeEventFilter(installed)
            installed.deleteLater()
            self.app._commonutils_pointer_entry = previous
