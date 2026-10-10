"""Live typed Markdown, selection wrapping and editor document/undo boundaries."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from commonUtils.tests.qt_test_case import QtTestCase

from PySide6.QtTest import QTest
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown.live_edit import FormattedMarkdownEdit, SourceMarkdownEdit


class LiveMarkdownTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.editor = FormattedMarkdownEdit()
        self.addCleanup(self.editor.deleteLater)

    def test_inactive_emphasis_markers_have_zero_advance_without_mutating_text(self):
        self.editor.setMarkdown('Before **bold** after\n\nElsewhere')
        source = self.editor.toPlainText()
        self.editor.resize(500, 300); self.editor.show()
        cursor = self.editor.textCursor(); cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        self.editor.setTextCursor(cursor); self.app.processEvents()
        line = self.editor.document().begin().layout().lineAt(0)
        self.assertAlmostEqual(line.cursorToX(7)[0], line.cursorToX(9)[0], places=2)
        self.assertAlmostEqual(line.cursorToX(13)[0], line.cursorToX(15)[0], places=2)
        cursor.setPosition(10); self.editor.setTextCursor(cursor); self.app.processEvents()
        line = self.editor.document().begin().layout().lineAt(0)
        self.assertGreater(line.cursorToX(9)[0] - line.cursorToX(7)[0], 1)
        self.assertEqual(self.editor.toPlainText(), source)

    def test_inactive_heading_has_zero_marker_width_and_keeps_source(self):
        self.editor.setMarkdown('###### Heading\n\nOther')
        self.editor.resize(500, 300)
        self.editor.show()
        cursor = self.editor.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)
        self.app.processEvents()
        block = self.editor.document().begin()
        line = block.layout().lineAt(0)
        self.assertAlmostEqual(line.cursorToX(7)[0], line.cursorToX(0)[0], places=2)
        cursor.setPosition(8)
        self.editor.setTextCursor(cursor)
        self.app.processEvents()
        self.assertGreater(block.layout().lineAt(0).cursorToX(7)[0], 10)
        self.assertTrue(self.editor.toPlainText().startswith('###### Heading'))
        self.assertIn('###### Heading', self.editor.document().toMarkdown())
        self.assertFalse(self.editor.document().isModified())

    def test_active_link_text_and_syntax_are_white_for_supported_forms(self):
        from commonUtils.ui.markdown.links import link_spans
        for text in ('[Label](target.md)', '[**Bold**](<target file.md>)',
                     '[[Page|Label]]', '[Page|Label]', '[Label](url \"Title\")'):
            with self.subTest(text=text):
                self.editor.setPlainText(text + ' after')
                cursor = self.editor.textCursor()
                cursor.setPosition(2)
                self.editor.setTextCursor(cursor)
                self.editor._highlighter.refresh_cursor()
                spans = list(link_spans(text))
                self.assertTrue(spans)
                block = self.editor.document().begin()
                for index in range(spans[0].start, spans[0].end):
                    fmt = next(qt.QTextCharFormat(item.format) for item in block.layout().formats()
                               if item.start <= index < item.start + item.length)
                    self.assertEqual(fmt.foreground().color(), qt.QColor('white'))
                cursor.movePosition(qt.QTextCursor.MoveOperation.End)
                self.editor.setTextCursor(cursor)
                self.assertEqual(self.editor.toPlainText(), text + ' after')

    def type(self, text):
        QTest.keyClicks(self.editor, text)

    def test_typed_heading_and_completed_bold_render_and_save(self):
        self.type('## New heading')
        self.assertEqual(self.editor.toPlainText(), '## New heading')
        self.assertEqual(self.editor.document().begin().blockFormat().headingLevel(), 2)
        self.assertIn('## New heading', self.editor.document().toMarkdown())
        self.editor.clear()
        self.editor.setCurrentCharFormat(qt.QTextCharFormat())
        self.type('A **bold** word')
        self.assertEqual(self.editor.toPlainText(), 'A **bold** word')
        self.assertIn('**bold**', self.editor.document().toMarkdown())
        self.assertNotIn('**bold word**', self.editor.document().toMarkdown())

    def test_partial_escaped_code_and_intraword_underscores_stay_literal(self):
        self.type('**unfinished')
        self.assertEqual(self.editor.toPlainText(), '**unfinished')
        self.editor.clear()
        self.type(r'\*literal\* foo_bar_baz')
        self.assertEqual(self.editor.toPlainText(), r'\*literal\* foo_bar_baz')
        self.editor.clear()
        self.type('`**literal**`')
        self.assertEqual(self.editor.toPlainText(), '`**literal**`')
        self.assertIn('`**literal**`', self.editor.document().toMarkdown())

    def test_italic_code_and_unicode_paste_do_not_damage_surrounding_blocks(self):
        self.editor.setMarkdown('| A | B |\n| --- | --- |\n| one | two |\n\nParagraph\n')
        cursor = self.editor.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        self.editor.setTextCursor(cursor)
        mime = qt.QMimeData()
        mime.setText('## New\nA *word*, **😀 bold**, and `**literal**`.')
        self.editor.insertFromMimeData(mime)
        self.assertIn('<table', self.editor.document().toHtml())
        text = self.editor.toPlainText()
        self.assertIn('😀 bold', text)
        markdown = self.editor.document().toMarkdown()
        self.assertIn('## New', markdown)
        self.assertIn('**😀 bold**', markdown)
        self.assertIn('`**literal**`', markdown)
        self.assertIn('*word*', markdown)

    def test_selected_star_wraps_then_second_star_bolds_without_replacing_text(self):
        self.editor.setPlainText('Selected words')
        self.editor.selectAll()
        self.type('*')
        self.assertEqual(self.editor.toPlainText(), '*Selected words*')
        self.assertIn('*Selected words*', self.editor.document().toMarkdown())
        self.assertTrue(self.editor.textCursor().hasSelection())
        self.type('*')
        self.assertIn('**Selected words**', self.editor.document().toMarkdown())
        self.assertNotIn('***Selected words***', self.editor.document().toMarkdown())
        self.editor.undo()
        self.assertIn('*Selected words*', self.editor.document().toMarkdown())
        self.editor.undo()
        self.assertNotIn('*', self.editor.document().toMarkdown())

    def test_source_selection_keeps_literal_delimiters_and_undo(self):
        source = SourceMarkdownEdit()
        self.addCleanup(source.deleteLater)
        source.setPlainText('😀 words')
        source.selectAll()
        QTest.keyClicks(source, '**')
        self.assertEqual(source.toPlainText(), '**😀 words**')
        self.assertEqual(source.textCursor().selectedText(), '😀 words')
        source.undo()
        self.assertEqual(source.toPlainText(), '*😀 words*')
        source.undo()
        self.assertEqual(source.toPlainText(), '😀 words')

    def test_autoformat_is_one_undo_step_and_readonly_never_wraps(self):
        self.type('**bold*')
        self.type('*')
        self.assertEqual(self.editor.toPlainText(), '**bold**')
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), '**bold*')
        self.editor.redo()
        self.assertEqual(self.editor.toPlainText(), '**bold**')
        self.editor.setReadOnly(True)
        self.editor.selectAll()
        self.type('*')
        self.assertEqual(self.editor.toPlainText(), '**bold**')

    def test_backspace_reveals_incomplete_inline_syntax_and_undo_restores_style(self):
        for marker in ('**', '__', '*', '_', '`'):
            with self.subTest(marker=marker):
                self.editor.setPlainText('')
                self.editor.setCurrentCharFormat(qt.QTextCharFormat())
                self.type(marker + 'word' + marker)
                self.assertEqual(self.editor.toPlainText(), marker + 'word' + marker)
                QTest.keyClick(self.editor, qt.Qt.Key.Key_Backspace)
                self.assertEqual(self.editor.toPlainText(), marker + 'word' + marker[:-1])
                cursor = self.editor.document().find('word')
                fmt = cursor.charFormat()
                self.assertLess(fmt.fontWeight(), qt.QFont.Weight.Bold)
                self.assertFalse(fmt.fontItalic())
                self.assertFalse(fmt.fontFixedPitch())
                self.editor.undo()
                self.assertEqual(self.editor.toPlainText(), marker + 'word' + marker)
                self.editor.redo()
                self.assertEqual(self.editor.toPlainText(), marker + 'word' + marker[:-1])
                self.type(marker[-1])
                self.assertEqual(self.editor.toPlainText(), marker + 'word' + marker)

    def test_delete_breaks_opening_marker_but_interior_backspace_edits_content(self):
        self.type('__bold__')
        cursor = self.editor.textCursor()
        cursor.setPosition(0)
        self.editor.setTextCursor(cursor)
        QTest.keyClick(self.editor, qt.Qt.Key.Key_Delete)
        self.assertEqual(self.editor.toPlainText(), '_bold__')
        self.editor.setPlainText('')
        self.editor.setCurrentCharFormat(qt.QTextCharFormat())
        self.type('**bold**')
        cursor = self.editor.textCursor()
        cursor.setPosition(4)
        self.editor.setTextCursor(cursor)
        QTest.keyClick(self.editor, qt.Qt.Key.Key_Backspace)
        self.assertEqual(self.editor.toPlainText(), '**bld**')
        self.assertIn('**bld**', self.editor.document().toMarkdown())

    def test_loaded_markdown_can_break_hidden_delimiters_without_touching_neighbors(self):
        self.editor.setMarkdown('Before **bold** after')
        cursor = self.editor.document().find('bold')
        cursor.setPosition(cursor.selectionEnd() + 2)
        self.editor.setTextCursor(cursor)
        QTest.keyClick(self.editor, qt.Qt.Key.Key_Backspace)
        self.assertEqual(self.editor.toPlainText(), 'Before **bold* after')

    def marker_size(self, position=0):
        block = self.editor.document().findBlock(position)
        offset = position - block.position()
        for span in block.layout().formats():
            if span.start <= offset < span.start + span.length:
                return span.format.font().pixelSize() if span.format.font().pixelSize() > 0 else span.format.fontPointSize()
        return 0

    def test_cursor_and_selection_reveal_markers_without_mutation_or_dirty_undo(self):
        self.editor.setMarkdown('Before **obsidian** after')
        self.editor.document().setModified(False)
        source = self.editor.document().toMarkdown()
        before = self.editor.toPlainText()
        cursor = self.editor.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)
        self.assertEqual(self.marker_size(7), 1)
        cursor.setPosition(7 + 2 + 3)
        self.editor.setTextCursor(cursor)
        self.assertEqual(self.marker_size(7), 0)
        self.assertEqual(self.editor.textCursor().position(), 12)
        cursor.setPosition(7 + 2 + len('obsidian'))
        self.editor.setTextCursor(cursor)
        self.assertEqual(self.marker_size(7), 0)
        cursor.setPosition(0)
        cursor.setPosition(10, qt.QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.assertEqual(self.marker_size(7), 0)
        cursor.clearSelection()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)
        self.assertEqual(self.marker_size(7), 1)
        self.assertEqual(self.editor.toPlainText(), before)
        self.assertEqual(self.editor.document().toMarkdown(), source)
        self.assertFalse(self.editor.document().isModified())
        self.assertFalse(self.editor.document().isUndoAvailable())

    def test_cursor_reveal_and_backspace_remove_format_without_repositioning(self):
        self.type('__obsidian__')
        cursor = self.editor.textCursor()
        cursor.setPosition(5)  # __obs|idian__
        self.editor.setTextCursor(cursor)
        self.assertEqual(self.marker_size(), 0)
        self.assertEqual(self.editor.textCursor().position(), 5)
        cursor.setPosition(len('__obsidian_'))
        self.editor.setTextCursor(cursor)
        QTest.keyClick(self.editor, qt.Qt.Key.Key_Backspace)
        self.assertEqual(self.editor.toPlainText(), '__obsidian_')
        self.assertEqual(self.marker_size(), 0)
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), '__obsidian__')
        self.assertEqual(self.editor.document().toMarkdown().strip(), '__obsidian__')

    def test_multiline_fences_keep_literal_code_and_language_on_export(self):
        self.type('```python')
        QTest.keyClick(self.editor, qt.Qt.Key.Key_Return)
        self.type('**literal**')
        QTest.keyClick(self.editor, qt.Qt.Key.Key_Return)
        self.type('value = 3')
        QTest.keyClick(self.editor, qt.Qt.Key.Key_Return)
        self.type('```')
        QTest.keyClick(self.editor, qt.Qt.Key.Key_Return)
        self.type('Outside')
        exported = self.editor.document().toMarkdown()
        self.assertIn('```python\n**literal**\nvalue = 3\n```', exported)
        self.assertIn('Outside', exported)
        block = self.editor.document().findBlockByNumber(1)
        self.assertTrue(any(item.format.fontFixedPitch() for item in block.layout().formats()))
        self.assertEqual(block.text(), '**literal**')
        self.assertFalse(self.editor.document().findBlockByNumber(4).blockFormat().nonBreakableLines())

    def test_loaded_fences_and_unfinished_fence_do_not_modify_on_navigation(self):
        self.editor.setMarkdown('```python\nx = 1\ny = 2\n```\n\nAfter')
        self.assertIn('```python\nx = 1\ny = 2\n```', self.editor.toPlainText())
        before = self.editor.document().toMarkdown()
        cursor = self.editor.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)
        self.assertEqual(self.editor.document().toMarkdown(), before)
        self.editor.setPlainText('```\n# not a heading\n**not bold**')
        self.editor._highlighter.rehighlight()
        self.assertIn('```\n# not a heading\n**not bold**', self.editor.document().toMarkdown())
        self.assertEqual(self.editor.document().toMarkdown().count('```'), 1)

    def test_loaded_escaped_markers_stay_literal_and_code_keeps_backslashes(self):
        source = r'\*\*literal\*\* and `a\*b`'
        self.editor.setMarkdown(source)
        self.assertIn(r'\*\*literal\*\*', self.editor.toPlainText())
        self.assertIn('`a\\*b`', self.editor.toPlainText())
        self.assertIn(r'\*\*literal\*\*', self.editor.document().toMarkdown())
        self.assertNotIn('**literal**', self.editor.document().toMarkdown())

    def test_fence_syntax_in_a_table_cell_does_not_capture_neighboring_cells(self):
        self.editor.setMarkdown('| A | B |\n| --- | --- |\n| one | two |\n')
        table = next(frame for frame in self.editor.document().rootFrame().childFrames()
                     if isinstance(frame, qt.QTextTable))
        self.editor.setTextCursor(table.cellAt(1, 0).firstCursorPosition())
        self.type('```')
        exported = self.editor.document().toMarkdown()
        self.assertIn('one', exported)
        self.assertIn('two', exported)
        self.assertIn('|', exported)

    def test_code_followed_by_table_has_no_extra_header_cell_on_export(self):
        self.editor.setMarkdown('```python\nx = 1\n```\n\n| Header | Value |\n| --- | --- |\n| Row | Cell |\n')
        exported = self.editor.document().toMarkdown()
        self.assertIn('```python\nx = 1\n```', exported)
        header = next(line for line in exported.splitlines() if 'Header' in line)
        self.assertEqual(header.count('|'), 3)
        self.assertIn('Value', header)
        self.assertIn('Row', exported)
        self.assertIn('Cell', exported)

    def test_unfinished_fence_before_an_existing_table_does_not_flatten_cells(self):
        self.editor.setMarkdown('Before\n\n| A | B |\n| --- | --- |\n| one | two |\n')
        cursor = self.editor.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.Start)
        self.editor.setTextCursor(cursor)
        self.type('```')
        exported = self.editor.document().toMarkdown()
        self.assertIn('```', exported)
        self.assertIn('|', exported)
        self.assertIn('one', exported)
        self.assertIn('two', exported)
