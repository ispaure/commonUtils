import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
from commonUtils.ui.code_editor.transforms import transform_lines


class TransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_pure_transforms_preserve_final_newline_and_unicode(self):
        self.assertEqual(transform_lines("b\na\nb\n", "unique"), "b\na\n")
        self.assertEqual(transform_lines("😀\na\n", "sort"), "a\n😀\n")
        self.assertEqual(transform_lines("x  \t\n", "trim"), "x\n")
        self.assertEqual(transform_lines("  x\ty", "tabs_to_spaces", 4), "  x y")
        self.assertEqual(transform_lines("      x  y", "spaces_to_tabs", 4), "\t  x  y")
        self.assertEqual(transform_lines("a\nb", "number", start=7), "7: a\n8: b")

    def test_selected_lines_one_undo_and_readonly(self):
        editor = CodeEdit()
        try:
            editor.setPlainText("keep\n😀 b\na\nlast\n")
            cursor = editor.textCursor()
            cursor.setPosition(5)
            cursor.setPosition(12, qt.QTextCursor.MoveMode.KeepAnchor)
            editor.setTextCursor(cursor)
            editor.transform("sort")
            self.assertEqual(editor.toPlainText(), "keep\na\n😀 b\nlast\n")
            editor.undo()
            self.assertEqual(editor.toPlainText(), "keep\n😀 b\na\nlast\n")
            editor.setReadOnly(True)
            editor.transform("upper")
            self.assertEqual(editor.toPlainText(), "keep\n😀 b\na\nlast\n")
        finally:
            editor.deleteLater()
