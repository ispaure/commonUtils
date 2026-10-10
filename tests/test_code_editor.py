import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from PySide6.QtTest import QTest
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit


class CodeEditorTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.editor = CodeEdit()
        self.addCleanup(self.editor.deleteLater)

    def test_diff_gutter_fits_unequal_line_numbers_after_font_changes(self):
        from types import SimpleNamespace
        from commonUtils.ui.code_editor.diff_bands import DiffEdit
        editor = DiffEdit()
        self.addCleanup(editor.deleteLater)
        rows = [SimpleNamespace(old='97', new='12345', kind=None)]
        editor.set_diff(SimpleNamespace(text=' context', lines=rows))
        editor.resize(500, 200); editor.show()
        for size in (10, 16, 24):
            font = qt.QFont(editor.font()); font.setPointSizeF(size)
            editor.setFont(font)
            self.app.processEvents()
            metrics = qt.QFontMetrics(editor.gutter_font())
            self.assertLess(editor.gutter_font().pointSizeF(), size)
            self.assertGreaterEqual(editor.gutter.width() // 2 - 12, metrics.horizontalAdvance('12345'))
            self.assertEqual(editor.gutter.width(), editor.gutter_width())
            self.assertFalse(editor.grab().isNull())
        editor.line_numbers = False; editor.update_gutter()
        self.assertEqual(editor.gutter_width(), 0)

    def test_line_edits_are_undoable_and_unicode_offsets_work(self):
        self.editor.setPlainText("😀 one\ntwo\nthree")
        cursor = self.editor.textCursor()
        cursor.setPosition(7)
        self.editor.setTextCursor(cursor)
        self.editor.move_lines(1)
        self.assertEqual(self.editor.toPlainText(), "😀 one\nthree\ntwo")
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), "😀 one\ntwo\nthree")
        cursor = self.editor.textCursor()
        cursor.setPosition(7)
        self.editor.setTextCursor(cursor)
        self.editor.duplicate()
        self.assertEqual(self.editor.toPlainText(), "😀 one\ntwo\ntwo\nthree")
        self.editor.delete_line()
        self.assertEqual(self.editor.toPlainText(), "😀 one\ntwo\nthree")

    def test_indent_comments_enter_and_gutter(self):
        self.editor.setPlainText("one\ntwo")
        self.editor.selectAll()
        self.editor.indent()
        self.assertEqual(self.editor.toPlainText(), "    one\n    two")
        self.editor.selectAll()
        self.editor.indent(True)
        self.editor.selectAll()
        self.editor.toggle_comment()
        self.assertEqual(self.editor.toPlainText(), "# one\n# two")
        self.editor.selectAll()
        self.editor.toggle_comment()
        self.assertEqual(self.editor.toPlainText(), "one\ntwo")
        self.editor.setPlainText("    value")
        self.editor.moveCursor(qt.QTextCursor.MoveOperation.End)
        QTest.keyClick(self.editor, qt.Qt.Key.Key_Return)
        self.assertEqual(self.editor.toPlainText(), "    value\n    ")
        self.assertGreater(self.editor.gutter_width(), 0)
        self.editor.line_numbers = False
        self.editor.update_gutter()
        self.assertEqual(self.editor.gutter_width(), 0)
