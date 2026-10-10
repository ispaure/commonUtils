import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from PySide6.QtTest import QTest
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit


class MultiCursorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.editor = CodeEdit()
        self.addCleanup(self.editor.deleteLater)

    def test_occurrences_typing_single_undo_and_wrap(self):
        self.editor.setPlainText("😀 foo foo foo")
        cursor = self.editor.textCursor()
        cursor.setPosition(3)
        self.editor.setTextCursor(cursor)
        for _ in range(4):
            self.editor.add_next_occurrence()
        self.assertEqual(len(self.editor.extra_cursors), 2)
        QTest.keyClicks(self.editor, "x")
        self.assertEqual(self.editor.toPlainText(), "😀 x x x")
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), "😀 foo foo foo")
        self.assertEqual(self.editor.extra_cursors, [])

    def test_rectangle_unicode_short_lines_paste_and_cut(self):
        self.editor.setPlainText("😀 abc\nq\n😀 xyz")
        cursor = self.editor.textCursor()
        cursor.setPosition(3)
        cursor.setPosition(13, qt.QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.rectangular_selection()
        self.assertEqual(len(self.editor.extra_cursors), 2)
        mime = qt.QMimeData()
        mime.setText("1\n2\n3")
        self.editor.insertFromMimeData(mime)
        self.assertEqual(self.editor.toPlainText(), "😀 1bc\nq2\n😀 3yz")
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), "😀 abc\nq\n😀 xyz")

    def test_delete_readonly_overlap_and_external_edits(self):
        self.editor.setPlainText("😀a\n😀b")
        cursors = []
        for position in (2, 6):
            cursor = self.editor.textCursor()
            cursor.setPosition(position)
            cursors.append(cursor)
        self.editor.set_cursors(cursors + cursors)
        self.assertEqual(len(self.editor.extra_cursors), 1)
        self.editor.setReadOnly(True)
        QTest.keyClick(self.editor, qt.Qt.Key.Key_Backspace)
        self.assertEqual(self.editor.toPlainText(), "😀a\n😀b")
        self.editor.setReadOnly(False)
        QTest.keyClick(self.editor, qt.Qt.Key.Key_Backspace)
        self.assertEqual(self.editor.toPlainText(), "a\nb")
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), "😀a\n😀b")

    def test_clipboard_cut_newline_pairing_and_escape(self):
        self.editor.setPlainText("a a")
        self.editor.add_next_occurrence()
        QTest.keySequence(self.editor, qt.QKeySequence(qt.QKeySequence.StandardKey.Copy))
        self.assertEqual(qt.QApplication.clipboard().text(), "a\na")
        QTest.keySequence(self.editor, qt.QKeySequence(qt.QKeySequence.StandardKey.Cut))
        self.assertEqual(self.editor.toPlainText(), " ")
        self.editor.undo()
        self.editor.add_next_occurrence()
        self.editor.auto_pairs = True
        QTest.keyClicks(self.editor, "(")
        self.assertEqual(self.editor.toPlainText(), "(a) (a)")
        QTest.keyClick(self.editor, qt.Qt.Key.Key_Escape)
        self.assertEqual(self.editor.extra_cursors, [])

    def test_input_method_commit_and_overlapping_selections(self):
        self.editor.setPlainText("abc abc")
        self.editor.add_next_occurrence()
        event = qt.QInputMethodEvent()
        event.setCommitString("é")
        self.editor.inputMethodEvent(event)
        self.assertEqual(self.editor.toPlainText(), "é é")
        self.editor.undo()
        a = qt.QTextCursor(self.editor.document())
        a.setPosition(0)
        a.setPosition(2, qt.QTextCursor.MoveMode.KeepAnchor)
        b = qt.QTextCursor(a)
        b.setPosition(1)
        b.setPosition(3, qt.QTextCursor.MoveMode.KeepAnchor)
        self.editor.set_cursors([a, b])
        self.assertEqual(self.editor.textCursor().selectedText(), "abc")
        self.assertEqual(self.editor.extra_cursors, [])
