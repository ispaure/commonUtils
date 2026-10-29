"""Shared link syntax, live edit round trips, and centralized Alt permission."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from PySide6.QtTest import QTest
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer, MarkdownWindow, open_markdown
from commonUtils.ui.markdown.live_edit import FormattedMarkdownEdit
from commonUtils.ui.markdown.links import link_spans, render_links


class MarkdownLinkTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.editor = FormattedMarkdownEdit()
        self.addCleanup(self.editor.deleteLater)

    def marker_size(self):
        return next(item.format.fontPointSize() for item in self.editor.document().begin().layout().formats()
                    if item.start == 0)

    def test_standard_and_alias_destinations(self):
        source = '[Web](https://example.com/a_(b)) [[Some page#details|Shown]] [Next|Go] [[Alone]]'
        spans = list(link_spans(source))
        self.assertEqual([span.target for span in spans],
                         ['https://example.com/a_(b)', 'Some%20page.md#details', 'Next.md', 'Alone.md'])
        self.assertEqual([source[s.content_start:s.content_end] for s in spans], ['Web', 'Shown', 'Go', 'Alone'])
        self.assertIn('[Shown](Some%20page.md#details)', render_links(source))

    def test_literal_code_escaped_links_and_images_remain_unchanged(self):
        source = '`[[Page|Label]]`\n```\n[[Page|Label]]\n```\n\\[[Page|Label]]\n![Image](image.png)\n'
        self.assertEqual(render_links(source), source)
        self.assertFalse(list(link_spans('`[web](https://example.com)` ![Image](image.png)')))

    def test_loaded_and_typed_links_keep_source_and_reveal_at_cursor(self):
        source = '[Web](https://example.com) [[Page|Alias]] [Page|Alias] [[Page]]'
        for loaded in (False, True):
            self.editor.clear()
            if loaded:
                self.editor.setMarkdown(source)
            else:
                QTest.keyClicks(self.editor, source)
            self.assertEqual(self.editor.toPlainText(), source)
            self.assertEqual(self.editor.document().toMarkdown().strip(), source)
            cursor = self.editor.textCursor()
            cursor.setPosition(2)
            self.editor.setTextCursor(cursor)
            self.assertNotEqual(self.marker_size(), 0.1)
            cursor.movePosition(qt.QTextCursor.MoveOperation.End)
            cursor.insertText(' after')
            self.editor.setTextCursor(cursor)
            formats = self.editor.document().begin().layout().formats()
            self.assertEqual(formats[0].format.font().pixelSize(), 1)

    def test_paired_local_links_preserve_label_and_target(self):
        source = '[thing|Show][LinkToFile]'
        span, = link_spans(source)
        self.assertEqual(source[span.content_start:span.content_end], 'Show')
        self.assertEqual(span.target, 'LinkToFile.md')
        self.assertEqual(render_links(source), '[Show](LinkToFile.md)')
        self.editor.setMarkdown('## ' + source + '\n\nOther')
        self.assertIn(source, self.editor.toPlainText())
        self.assertIn(source, self.editor.document().toMarkdown())

    def test_reference_links_resolve_definitions_and_round_trip(self):
        source = '## [Website][site]\n\n[site]: https://example.com\n'
        self.assertIn('[Website](https://example.com)', render_links(source))
        self.editor.setMarkdown(source)
        exported = self.editor.document().toMarkdown()
        self.assertIn('[Website][site]', exported)
        self.assertIn('[site]: https://example.com', exported)

    def test_hover_keeps_links_and_heading_collapsed_without_moving_caret(self):
        source = '## [Website](https://example.com)\n\nOther'
        self.editor.setMarkdown(source)
        source = self.editor.toPlainText()
        self.editor.resize(700, 250)
        self.editor.show()
        cursor = self.editor.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)
        self.app.processEvents()
        block = self.editor.document().begin()
        line = block.layout().lineAt(0)
        self.assertAlmostEqual(line.cursorToX(3)[0], line.cursorToX(4)[0], places=2)
        hit = qt.QTextCursor(block)
        hit.setPosition(7)
        point = self.editor.cursorRect(hit).center()
        QTest.mouseMove(self.editor.viewport(), point)
        self.app.processEvents()
        self.assertAlmostEqual(block.layout().lineAt(0).cursorToX(4)[0], 0, places=2)
        self.assertEqual(self.editor.textCursor().position(), cursor.position())
        self.assertEqual(self.editor.toPlainText(), source)
        self.assertFalse(self.editor.document().isModified())
        self.assertFalse(self.editor.document().isUndoAvailable())
        self.editor.leaveEvent(qt.QEvent(qt.QEvent.Type.Leave))
        self.app.processEvents()
        line = block.layout().lineAt(0)
        self.assertAlmostEqual(line.cursorToX(3)[0], line.cursorToX(4)[0], places=2)

    def test_alias_preview_links_navigate_and_keep_edit_permission(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / 'first.md', root / 'Second page.md'
            first.write_text('[[Second page|Next]]\n')
            second.write_text('# Second\n')
            viewer = MarkdownViewer(first, allow_edit=True)
            self.addCleanup(viewer.deleteLater)
            self.assertIn('Next', viewer.browser.toPlainText())
            self.assertNotIn('[[', viewer.browser.toPlainText())
            viewer.follow_link(qt.QUrl(list(link_spans(first.read_text()))[0].target))
            self.assertEqual(viewer.current_path, second.resolve())
            self.assertTrue(viewer.allow_edit)

    def test_plain_and_ctrl_click_follow_links_but_syntax_click_edits(self):
        self.editor.setMarkdown('[Web](https://example.com)')
        self.editor.resize(600, 160)
        self.editor.show()
        cursor = self.editor.textCursor()
        cursor.setPosition(2)
        self.editor.setTextCursor(cursor)
        self.app.processEvents()
        point = self.editor.cursorRect(cursor).center()
        with patch.object(self.editor, 'linkActivated') as activated:
            QTest.mouseClick(self.editor.viewport(), qt.Qt.MouseButton.LeftButton,
                             qt.Qt.KeyboardModifier.NoModifier, point)
            activated.emit.assert_called_once_with(qt.QUrl('https://example.com'))
            activated.emit.reset_mock()
            QTest.mouseClick(self.editor.viewport(), qt.Qt.MouseButton.LeftButton,
                             qt.Qt.KeyboardModifier.ControlModifier, point)
            activated.emit.assert_called_once_with(qt.QUrl('https://example.com'))
            activated.emit.reset_mock()
            cursor.setPosition(0)
            point = self.editor.cursorRect(cursor).center()
            QTest.mouseClick(self.editor.viewport(), qt.Qt.MouseButton.LeftButton,
                             qt.Qt.KeyboardModifier.NoModifier, point)
            activated.emit.assert_not_called()

    def test_navigation_clears_old_selection_in_read_and_formatted_modes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / 'first.md', root / 'second.md'
            first.write_text('[Next](second.md)\n\nOther text')
            second.write_text('# Second\n\nA new document with enough text for the old selection.')
            viewer = MarkdownViewer(first, allow_edit=True)
            self.addCleanup(viewer.deleteLater)
            viewer.resize(700, 400)
            viewer.show()
            for editing in (False, True):
                with self.subTest(editing=editing):
                    viewer.open_document(first)
                    viewer.set_editing(editing)
                    viewer.browser.selectAll()
                    target = viewer.active_editor() if editing else viewer.browser
                    if editing:
                        cursor = target.textCursor()
                        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
                        target.setTextCursor(cursor)
                        cursor.setPosition(3)
                    else:
                        cursor = target.document().find('Next')
                        # Click inside the label, not its trailing glyph boundary:
                        # font metrics differ across the headless platform runners.
                        cursor.setPosition(cursor.selectionStart() + 2)
                    self.app.processEvents()
                    point = target.cursorRect(cursor).center()
                    if not editing:
                        self.assertTrue(target.anchorAt(point).endswith('second.md'))
                    QTest.mouseClick(target.viewport(), qt.Qt.MouseButton.LeftButton,
                                     qt.Qt.KeyboardModifier.NoModifier, point)
                    self.assertEqual(viewer.current_path, second.resolve())
                    self.assertFalse(viewer.browser.textCursor().hasSelection())
                    self.assertFalse(viewer.formatted_editor.textCursor().hasSelection())
                    self.assertFalse(viewer.is_modified)
                    viewer.browser.selectAll()
                    viewer.back()
                    self.assertEqual(viewer.current_path, first.resolve())
                    self.assertFalse(viewer.browser.textCursor().hasSelection())
                    viewer.forward()
                    self.assertEqual(viewer.current_path, second.resolve())
                    self.assertFalse(viewer.browser.textCursor().hasSelection())

    def test_drag_and_shift_click_select_link_text_without_navigation(self):
        self.editor.setMarkdown('[Next](page.md) after')
        self.editor.resize(600, 160)
        self.editor.show()
        cursor = self.editor.textCursor()
        cursor.setPosition(2)
        self.editor.setTextCursor(cursor)
        self.app.processEvents()
        point = self.editor.cursorRect(cursor).center()
        with patch.object(self.editor, 'linkActivated') as activated:
            QTest.mouseClick(self.editor.viewport(), qt.Qt.MouseButton.LeftButton,
                             qt.Qt.KeyboardModifier.ShiftModifier, point)
            activated.emit.assert_not_called()
            QTest.mousePress(self.editor.viewport(), qt.Qt.MouseButton.LeftButton,
                             qt.Qt.KeyboardModifier.NoModifier, point)
            cursor.setPosition(5)
            end = self.editor.cursorRect(cursor).center()
            QTest.mouseMove(self.editor.viewport(), end)
            QTest.mouseRelease(self.editor.viewport(), qt.Qt.MouseButton.LeftButton,
                               qt.Qt.KeyboardModifier.NoModifier, end)
            activated.emit.assert_not_called()
            self.assertTrue(self.editor.textCursor().hasSelection())

    def test_same_document_restyle_preserves_reading_selection(self):
        viewer = MarkdownViewer(allow_edit=True)
        self.addCleanup(viewer.deleteLater)
        viewer._render_source('Selectable text')
        viewer.browser.selectAll()
        selected = viewer.browser.textCursor().selectedText()
        viewer._render_source('Selectable text')
        self.assertEqual(viewer.browser.textCursor().selectedText(), selected)

    def test_alt_is_handled_by_window_and_helper_without_caller_flags(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'guide.md'
            path.write_text('# Guide\n')
            for factory in (MarkdownWindow, open_markdown):
                with patch.object(qt.QApplication, 'keyboardModifiers', return_value=qt.Qt.KeyboardModifier.AltModifier):
                    window = factory(path)
                self.assertTrue(window.viewer.allow_edit)
                self.assertTrue(window.viewer.edit_button.isChecked())
                window.close()
            with patch.object(qt.QApplication, 'keyboardModifiers', return_value=qt.Qt.KeyboardModifier.NoModifier):
                window = MarkdownWindow(path)
            self.assertFalse(window.viewer.allow_edit)
            window.close()
