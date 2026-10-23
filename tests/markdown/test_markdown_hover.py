"""Read-only pointer-bound previews do not navigate or open linked editors."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer


class MarkdownHoverTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_hover_lifetime_and_edit_mode(self):
        with self.temporary_directory() as temporary:
            root = Path(temporary).resolve()
            page, target = root / 'README.md', root / 'sample.py'
            page.write_text('# Home\n\n[Next](sample.py)\n\nNormal text')
            target.write_text('print("preview only")\n' + 'another line\n' * 50)
            viewer = MarkdownViewer(page, allow_edit=True)
            viewer.set_editing(False)
            viewer.resize(650, 450)
            viewer.show()
            self.app.processEvents()
            browser = viewer.browser
            cursor = browser.document().find('Next')
            cursor.setPosition(cursor.selectionStart() + 1)
            point = browser.cursorRect(cursor).center()
            self.assertEqual(browser.anchorAt(point), 'sample.py')
            history = list(viewer.history)
            with patch('commonUtils.ui.text_editor.open_text_file') as opened:
                event = qt.QMouseEvent(qt.QEvent.Type.MouseMove, qt.QPointF(point),
                    qt.QPointF(browser.viewport().mapToGlobal(point)), qt.Qt.MouseButton.NoButton,
                    qt.Qt.MouseButton.NoButton, qt.Qt.KeyboardModifier.NoModifier)
                self.app.sendEvent(browser.viewport(), event)
                self.assertTrue(viewer.link_preview.popup.isVisible())
                self.assertIn('preview only', viewer.link_preview.snippet.toPlainText())
                self.assertLessEqual(len(viewer.link_preview.snippet.toPlainText()), 2402)
                self.assertEqual(viewer.link_preview.title.text(), 'sample.py')
                opened.assert_not_called()
            self.assertEqual(viewer.history, history)
            self.assertEqual(viewer.current_path, page)
            self.app.sendEvent(browser.viewport(), qt.QEvent(qt.QEvent.Type.Leave))
            self.assertFalse(viewer.link_preview.popup.isVisible())
            self.assertEqual(viewer.link_preview.snippet.toPlainText(), '')
            viewer.link_preview.show_link('sample.py', viewer.mapToGlobal(qt.QPoint(50, 50)))
            self.assertTrue(viewer.link_preview.popup.isVisible())
            viewer.set_editing(True)
            self.assertFalse(viewer.link_preview.popup.isVisible())
            viewer.link_preview.show_link('sample.py', viewer.mapToGlobal(qt.QPoint(50, 50)))
            self.assertFalse(viewer.link_preview.popup.isVisible())
            viewer.close()

    def test_markdown_is_formatted_and_switching_to_code_keeps_literal_text(self):
        with self.temporary_directory() as temporary:
            root = Path(temporary).resolve()
            page, target, code = root / 'home.md', root / 'other.MARKDOWN', root / 'example.py'
            page.write_text('# Home')
            target.write_text('---\ntags: [guide]\n---\n# Heading\n\n**Bold** and *italic*\n\n'
                              '- First\n- Second\n\n| Name | Value |\n| --- | --- |\n| Item | 2 |')
            code.write_text('# Literal heading\n**literal markers**\n<script>literal</script>')
            viewer = MarkdownViewer(page)
            viewer.show()
            self.app.processEvents()
            preview = viewer.link_preview
            history = list(viewer.history)
            position = viewer.mapToGlobal(qt.QPoint(50, 50))
            preview.show_link('other.MARKDOWN', position)
            document = preview.snippet.document()
            self.assertEqual(document.begin().blockFormat().headingLevel(), 1)
            self.assertIn('Heading', preview.snippet.toPlainText())
            self.assertNotIn('# Heading', preview.snippet.toPlainText())
            self.assertNotIn('tags:', preview.snippet.toPlainText())
            self.assertNotIn('**Bold**', preview.snippet.toPlainText())
            self.assertGreaterEqual(document.find('Bold').charFormat().fontWeight(), qt.QFont.Weight.Bold)
            self.assertTrue(document.find('italic').charFormat().fontItalic())
            self.assertIsNotNone(document.find('First').currentList())
            self.assertIsNotNone(document.find('Item').currentTable())
            self.assertFalse(preview.snippet.openLinks())
            self.assertFalse(preview.snippet.openExternalLinks())
            preview.show_link('example.py', position)
            self.assertEqual(preview.snippet.toPlainText(), code.read_text())
            self.assertEqual(document.begin().blockFormat().headingLevel(), 0)
            self.assertEqual(viewer.current_path, page)
            self.assertEqual(viewer.history, history)
            viewer.close()

    def test_markdown_resources_are_blocked_and_html_stays_literal(self):
        with self.temporary_directory() as temporary:
            root = Path(temporary).resolve()
            page, target = root / 'home.md', root / 'other.md'
            page.write_text('# Home')
            target.write_text('# Heading\n\n![Local](image.png)\n\n'
                              '![Remote](https://example.org/image.png)\n\n<script>literal</script>')
            viewer = MarkdownViewer(page)
            preview = viewer.link_preview
            preview.show_link('other.md', viewer.mapToGlobal(qt.QPoint(50, 50)))
            document = preview.snippet.document()
            for resource in (qt.QUrl.fromLocalFile(str(root / 'image.png')),
                             qt.QUrl('https://example.org/image.png')):
                self.assertIsNone(document.resource(qt.QTextDocument.ResourceType.ImageResource, resource))
            self.assertIn('<script>literal</script>', preview.snippet.toPlainText())
            viewer.close()

    def test_relative_markdown_missing_binary_external_and_nonlink(self):
        with self.temporary_directory() as temporary:
            root = Path(temporary).resolve()
            folder = root / 'guide'
            folder.mkdir()
            page = folder / 'page.md'
            page.write_text('# Page')
            (root / 'other.md').write_text('# Other\n\nPreview body')
            (root / 'binary.bin').write_bytes(b'\x00\x01\x02')
            viewer = MarkdownViewer(page)
            viewer.show()
            self.app.processEvents()
            preview = viewer.link_preview
            position = viewer.mapToGlobal(qt.QPoint(50, 50))
            preview.show_link('../other', position)
            self.assertTrue(preview.popup.isVisible())
            self.assertIn('Preview body', preview.snippet.toPlainText())
            preview.show_link('', position)
            self.assertFalse(preview.popup.isVisible())
            for link in ('../missing.md', '../binary.bin', 'https://example.org/page.md'):
                preview.show_link(link, position)
                self.assertFalse(preview.popup.isVisible(), link)
            self.assertEqual(viewer.status.text(), '')
            viewer.close()
