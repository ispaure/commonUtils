"""Markdown rendering, local link history, failures and browser activation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from commonUtils.fileTypes.registry import file_from_path
from commonUtils.fileTypes.markdownType import MarkdownFile
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer, open_markdown, _windows
from commonUtils.ui.file_browser import FileBrowser


class MarkdownTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.first = self.root / 'first.md'
        self.second = self.root / 'second page.MD'
        self.first.write_text('# First\n\n[Next](second%20page.MD#details)\n\n'
                              '| Name | Value |\n| --- | --- |\n| One | Two |\n\n'
                              '```python\nprint("example")\n```\n', encoding='utf-8')
        self.second.write_text('# Second\n\n## Details\n\nText\n\n## Details\n\nMore\n', encoding='utf-8')
        self.viewer = MarkdownViewer(self.first)
        self.viewer.resize(600, 400)
        self.viewer.show()
        self.addCleanup(self.viewer.deleteLater)
        self.app.processEvents()

    def test_rendering_tables_headings_code_and_heading_fragments(self):
        html = self.viewer.browser.document().toHtml()
        self.assertIn('<table', html)
        self.assertIn('print(', self.viewer.browser.toPlainText())
        self.assertEqual(self.viewer.browser.document().begin().blockFormat().headingLevel(), 1)
        self.viewer.follow_link(qt.QUrl('second%20page.MD#details'))
        self.assertEqual(self.viewer.current_path, self.second.resolve())
        anchors = []
        block = self.viewer.browser.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel():
                cursor = qt.QTextCursor(block)
                cursor.movePosition(qt.QTextCursor.MoveOperation.NextCharacter, qt.QTextCursor.MoveMode.KeepAnchor)
                anchors.extend(cursor.charFormat().anchorNames())
            block = block.next()
        self.assertIn('details', anchors)
        self.assertIn('details-1', anchors)

    def test_back_forward_anchor_navigation_and_branching_history(self):
        self.viewer.follow_link(qt.QUrl('second%20page.MD'))
        self.viewer.follow_link(qt.QUrl('#details'))
        self.assertEqual(len(self.viewer.history), 3)
        self.viewer.back()
        self.assertEqual(self.viewer.history_index, 1)
        self.viewer.back()
        self.assertEqual(self.viewer.current_path, self.first.resolve())
        self.viewer.forward()
        self.assertEqual(self.viewer.current_path, self.second.resolve())
        self.viewer.open_document(self.first)
        self.assertFalse(self.viewer.forward_button.isEnabled())
        self.assertEqual(len(self.viewer.history), 3)

    def test_failed_navigation_preserves_document_and_history(self):
        before = self.viewer.browser.toPlainText()
        for link in ('missing.md', 'source.py', 'bad.md'):
            if link == 'bad.md':
                (self.root / link).write_bytes(b'\xff')
            self.viewer.follow_link(qt.QUrl(link))
            self.assertEqual(self.viewer.current_path, self.first.resolve())
            self.assertEqual(self.viewer.browser.toPlainText(), before)
            self.assertEqual(len(self.viewer.history), 1)
            self.assertIn('Cannot open', self.viewer.status.text())
        self.viewer.follow_link(qt.QUrl('javascript:alert(1)'))
        self.assertIn('Unsupported link', self.viewer.status.text())

    def test_external_links_use_default_application_without_changing_history(self):
        with patch.object(qt.QDesktopServices, 'openUrl', return_value=True) as opened:
            self.viewer.follow_link(qt.QUrl('https://example.com/help'))
        opened.assert_called_once()
        self.assertEqual(len(self.viewer.history), 1)

    def test_back_to_removed_file_keeps_current_page(self):
        self.viewer.open_document(self.second)
        self.first.unlink()
        self.viewer.back()
        self.assertEqual(self.viewer.current_path, self.second.resolve())
        self.assertEqual(self.viewer.history_index, 1)
        self.assertIn('Cannot open', self.viewer.status.text())

    def test_local_images_scroll_restoration_and_signal_path(self):
        image = qt.QImage(8, 8, qt.QImage.Format.Format_RGB32)
        image.fill(qt.QColor('red'))
        image.save(str(self.root / 'cover.png'))
        self.first.write_text('# First\n\n![Cover](cover.png)\n\n' +
                              '\n\n'.join(f'Paragraph {index}' for index in range(100)), encoding='utf-8')
        observed = []
        self.viewer.path_changed.connect(lambda path: observed.append((path, self.viewer.current_path)))
        self.viewer.open_document(self.first)
        self.app.processEvents()
        resource = self.viewer.browser.document().resource(qt.QTextDocument.ResourceType.ImageResource,
                                                           qt.QUrl('cover.png'))
        self.assertIsNotNone(resource)
        self.assertFalse(resource.isNull())
        self.viewer.browser.verticalScrollBar().setValue(150)
        original_scroll = self.viewer.browser.verticalScrollBar().value()
        self.assertGreater(original_scroll, 0)
        self.viewer.open_document(self.second)
        self.viewer.back()
        self.assertEqual(self.viewer.browser.verticalScrollBar().value(), original_scroll)
        self.assertTrue(all(path == current for path, current in observed))

    def test_window_lifetime_and_browser_markdown_activation(self):
        self.assertIsInstance(file_from_path(self.second), MarkdownFile)
        self.assertIsInstance(file_from_path('missing.markdown'), MarkdownFile)
        window = open_markdown(self.first)
        self.assertIn(window, _windows)
        window.close()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.assertNotIn(window, _windows)
        browser = FileBrowser(self.root)
        self.addCleanup(browser.deleteLater)
        self.addCleanup(browser.shutdown)
        index = browser.model.index(str(self.second))
        deadline = time.monotonic() + 2
        while not index.isValid() and time.monotonic() < deadline:
            self.app.processEvents()
            index = browser.model.index(str(self.second))
        self.assertTrue(index.isValid())
        with patch('commonUtils.ui.markdown.open_markdown') as opened:
            browser._activate(index)
        opened.assert_called_once_with(self.second, parent=browser.window())
