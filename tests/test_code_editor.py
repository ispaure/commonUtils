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

    def test_shared_view_can_detach_and_reattach_without_old_document_hooks(self):
        other = CodeEdit()
        self.addCleanup(other.deleteLater)
        self.editor.setPlainText('one\ntwo')
        self.editor.indent_width = 2
        self.editor.use_tabs = True
        other.share_document_from(self.editor)
        other.share_document_from(self.editor)
        self.assertEqual(other.indent_width, 2)
        self.assertTrue(other.use_tabs)
        self.assertIs(other.folding, self.editor.folding)
        self.assertEqual(sum(ref() is other for ref in other.folding.views), 1)
        other.insertPlainText('shared')
        self.assertIn('shared', self.editor.toPlainText())
        other.detach_document()
        self.assertFalse(any(ref() is other for ref in self.editor.folding.views))
        other.setPlainText('independent')
        self.editor.insertPlainText('original')
        self.assertEqual(other.toPlainText(), 'independent')
        other.share_document_from(self.editor)
        self.assertIs(other.document(), self.editor.document())
        self.assertEqual(sum(ref() is other for ref in other.folding.views), 1)
        other.detach_document()

    def test_highlighter_rebind_survives_old_view_destruction_and_palette_change(self):
        from commonUtils.ui.code_editor.syntax import SyntaxHighlighter
        owner = qt.QWidget()
        source, target = CodeEdit(owner), CodeEdit(owner)
        source.document().setParent(owner)
        source.setPlainText('value = 1\n')
        target.share_document_from(source)
        highlighter = SyntaxHighlighter(source, 'python')
        with self.assertRaises(ValueError):
            highlighter.rebind_editor(self.editor)
        highlighter.rebind_editor(target)
        self.assertIs(highlighter.theme_timer.parent(), highlighter)
        source.detach_document()
        source.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        target.insertPlainText('# edit\n')
        palette = target.palette()
        palette.setColor(qt.QPalette.ColorRole.Base, qt.QColor('#101010'))
        target.setPalette(palette)
        self.app.processEvents()
        self.assertIs(highlighter.editor, target)
        self.assertIs(highlighter.document(), target.document())
        self.assertEqual(target.comment_prefix, '#')
        self.assertTrue(target.document().firstBlock().layout().formats())

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

    def test_gutter_tracks_font_and_digit_growth_without_window_resize(self):
        self.editor.resize(600, 300)
        self.editor.show()
        self.app.processEvents()
        for size, lines in ((14, 9), (24, 1000), (10, 10), (48, 10000)):
            self.editor.set_font_size(size)
            self.editor.setPlainText('\n'.join('line' for _ in range(lines)))
            self.app.processEvents()
            self.assertEqual(self.editor.gutter.width(), self.editor.gutter_width())
            self.assertEqual(self.editor.viewportMargins().left(), self.editor.gutter.width())
            self.assertGreaterEqual(self.editor.gutter.width() - 28,
                                    self.editor.fontMetrics().horizontalAdvance(str(lines)))

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
