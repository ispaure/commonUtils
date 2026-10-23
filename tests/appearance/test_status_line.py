"""Shared footer messages remain readable without controlling workspace height."""
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.status_line import StatusLine, style_status_bar
from commonUtils.ui.file_browser.status import IndexStatusLabel


class StatusLineTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_long_message_retains_full_text_and_clear_retires_it(self):
        label = StatusLine()
        label.resize(160, 32)
        text = 'Long status\nwith additional details ' * 50
        label.setText(text)
        label.show(); self.app.processEvents()
        self.assertEqual(label.text(), text)
        self.assertEqual(label.toolTip(), text)
        self.assertFalse(label.wordWrap())
        self.assertLess(label.height(), 50)
        label.clear()
        self.assertEqual(label.text(), '')
        self.assertEqual(label.toolTip(), '')

    def test_file_browser_uses_same_font_and_retains_specialized_padding(self):
        footer = StatusLine('Ready')
        self.assertEqual(footer.toolTip(), 'Ready')
        browser = IndexStatusLabel()
        self.assertEqual(footer.font().pointSize(), browser.font().pointSize())
        self.assertEqual(footer.foregroundRole(), qt.QPalette.ColorRole.PlaceholderText)
        self.assertTrue(footer.font().italic())
        self.assertEqual(browser.contentsMargins().top(), 0)

    def test_native_status_bar_keeps_timed_message_and_permanent_controls(self):
        window = qt.QMainWindow()
        bar = window.statusBar()
        control = qt.QPushButton('Details')
        bar.addPermanentWidget(control)
        style_status_bar(bar)
        bar.showMessage('Saved', 1000)
        self.assertEqual(bar.currentMessage(), 'Saved')
        self.assertFalse(bar.isSizeGripEnabled())
        self.assertIs(control.parentWidget(), bar)

    def test_application_styling_does_not_reenter_footer_font_callback(self):
        from commonUtils.ui.appearance.styling import apply_styling
        controller = apply_styling(self.app)
        calls = []
        original = controller._update_font
        def tracked(widget, role, callback):
            calls.append(widget)
            self.assertLess(len(calls), 50, 'Font update reentered recursively')
            return original(widget, role, callback)
        from unittest.mock import patch
        with patch.object(controller, '_update_font', side_effect=tracked):
            label = StatusLine('Ready')
            label.show()
            self.app.processEvents()
            font = label.font()
            font.setPointSize(font.pointSize() + 1)
            label.setFont(font)
            self.app.processEvents()
        self.assertTrue(label.font().italic())
        self.assertEqual(label.font().pointSize(), controller.font('ui').pointSize())
