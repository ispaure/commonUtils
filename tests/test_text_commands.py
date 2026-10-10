from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.text_commands import wrap_selection


class TextCommandTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_unicode_selection_and_one_step_undo_in_both_editor_engines(self):
        for editor in (qt.QPlainTextEdit(), qt.QTextEdit()):
            editor.setPlainText('😀 words')
            editor.selectAll()
            wrap_selection(editor, '**')
            self.assertEqual(editor.toPlainText(), '**😀 words**')
            self.assertEqual(editor.textCursor().selectedText(), '😀 words')
            editor.undo()
            self.assertEqual(editor.toPlainText(), '😀 words')
            editor.setReadOnly(True)
            self.assertFalse(wrap_selection(editor, '*'))
            self.assertEqual(editor.toPlainText(), '😀 words')
