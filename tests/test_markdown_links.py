"""Shared link syntax, live edit round trips, and centralized Alt permission."""
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
            self.editor.setTextCursor(cursor)
            self.assertEqual(self.marker_size(), 0.1)

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

    def test_ctrl_click_follows_but_plain_click_edits(self):
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
            activated.emit.assert_not_called()
            QTest.mouseClick(self.editor.viewport(), qt.Qt.MouseButton.LeftButton,
                             qt.Qt.KeyboardModifier.ControlModifier, point)
            activated.emit.assert_called_once_with(qt.QUrl('https://example.com'))

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
