"""Responsive image layout preserves authored sizes, source and undo boundaries."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown.live_edit import FormattedMarkdownEdit
from commonUtils.ui.markdown.images import prepare_wiki_images
from commonUtils.ui.markdown import MarkdownViewer
from commonUtils.tests.test_gif_headers import GIF


class MarkdownImageSizeTests(QtTestCase):
    def setUp(self):
        self.scope = self.temporary_directory()
        self.root = Path(self.scope.name).resolve()
        self.image = qt.QImage(1600, 800, qt.QImage.Format.Format_RGB32)
        self.image.fill(qt.QColor('red'))
        self.assertTrue(self.image.save(str(self.root / 'large.png')))
        (self.root / 'animated.gif').write_bytes(GIF)
        self.editor = FormattedMarkdownEdit()
        self.editor.document().setBaseUrl(qt.QUrl.fromLocalFile(str(self.root) + '/'))
        self.editor.resize(700, 400)
        self.editor.show()

    def dimensions(self):
        qt.QApplication.processEvents()
        line = self.editor.document().begin().layout().lineAt(0)
        return line.naturalTextWidth(), line.height()

    def test_oversized_image_fits_after_shrink_and_grows_again_without_edits(self):
        source = '![Large](large.png)'
        self.editor.setMarkdown(source)
        for width in (700, 250, 500):
            self.editor.resize(width, 400)
            shown, height = self.dimensions()
            available = self.editor.viewport().width() - self.editor.document().documentMargin() * 2
            self.assertLessEqual(shown, available)
            self.assertAlmostEqual(shown / height, 2, delta=.03)
            self.assertEqual(self.editor.document().toMarkdown().strip(), source)
            self.assertFalse(self.editor.document().isModified())
            self.assertFalse(self.editor.document().isUndoAvailable())

    def test_explicit_wiki_and_markdown_dimensions_survive_resize_and_edit(self):
        for source in ('![[large.png|400]]', '![Caption|400](large.png)', '![400](large.png)',
                       '![[large.png|400x100]]', '![Caption|400x100](large.png)'):
            with self.subTest(source=source):
                self.editor.resize(700, 400)
                self.editor.setMarkdown(source)
                shown, height = self.dimensions()
                self.assertEqual(shown, 400)
                ratio = 4 if '400x100' in source else 2
                self.assertAlmostEqual(shown / height, ratio, delta=.05)
                self.editor.resize(250, 400)
                shown, height = self.dimensions()
                self.assertLessEqual(shown, 240)
                self.assertAlmostEqual(shown / height, ratio, delta=.05)
                self.assertEqual(self.editor.document().toMarkdown().strip(), source)
                self.editor.moveCursor(qt.QTextCursor.MoveOperation.End)
                self.editor.insertPlainText(' Edited')
                self.assertIn(source, self.editor.document().toMarkdown())
                self.editor.undo()
                self.assertEqual(self.editor.document().toMarkdown().strip(), source)

    def test_wiki_images_in_read_and_edit_modes_keep_animation_and_source(self):
        source = '![[animated.gif|400]]'
        path = self.root / 'note.md'
        path.write_text(source)
        viewer = MarkdownViewer(path, allow_edit=True)
        viewer.show()
        self.wait_until(lambda: bool(viewer.formatted_editor.animated_images.movies), message='sized wiki GIF editor')
        self.assertEqual(viewer.formatted_editor.document().toMarkdown().strip(), source)
        viewer.set_editing(False)
        self.wait_until(lambda: bool(viewer.browser.animated_images.movies), message='sized wiki GIF reader')
        self.assertFalse(viewer.is_modified)
        self.assertEqual(viewer.markdown_text(), source)

    def test_fences_inline_code_escapes_and_nonimage_embeds_stay_literal(self):
        for text in ('`![[large.png|400]]`', '```\n![[large.png|400]]\n```',
                     '~~~\n![[large.png|400]]\n~~~', '\\![[large.png|400]]',
                     '    ![[large.png|400]]', '![[Note|400]]', '![[document.pdf|400]]',
                     '> ```\n> ![[large.png|400]]\n> ```'):
            with self.subTest(text=text):
                prepared, tokens = prepare_wiki_images(text)
                self.assertEqual(prepared, text)
                self.assertFalse(tokens)

    def test_high_density_resources_keep_their_logical_size(self):
        image = qt.QImage(200, 100, qt.QImage.Format.Format_RGB32)
        image.fill(qt.QColor('blue'))
        image.setDevicePixelRatio(2)
        url = self.editor.document().baseUrl().resolved(qt.QUrl('retina.png'))
        self.editor.document().addResource(qt.QTextDocument.ResourceType.ImageResource, url, image)
        fmt = qt.QTextImageFormat()
        fmt.setName('retina.png')
        self.editor.textCursor().insertImage(fmt)
        width, height = self.dimensions()
        self.assertEqual((width, height), (100, 50))

    def test_image_to_text_gap_stays_small_in_reader_and_formatted_editor(self):
        for embed in ('![Large](large.png)', '![[large.png|400x300]]'):
            source = embed + '\n\nFollowing text\n'
            path = self.root / 'note.md'
            path.write_text(source)
            viewer = MarkdownViewer(path, allow_edit=True)
            viewer.set_editing(False)
            viewer.show()
            for surface in (viewer.browser, viewer.formatted_editor):
                for width in (700, 320):
                    with self.subTest(embed=embed, surface=type(surface).__name__, width=width):
                        viewer.resize(width, 600)
                        # The editor is hidden while reading; give it a layout
                        # allocation too, as when switching into Formatted mode.
                        if surface is viewer.formatted_editor:
                            viewer.set_editing(True)
                            viewer.set_edit_mode('formatted')
                        qt.QApplication.processEvents()
                        document = surface.document()
                        block = document.begin()
                        layout = document.documentLayout()
                        image_rect = layout.blockBoundingRect(block)
                        text_rect = layout.blockBoundingRect(block.next())
                        self.assertGreater(image_rect.height(), 100)
                        gap = text_rect.top() - image_rect.bottom()
                        self.assertLessEqual(gap, 20)
                        self.assertGreaterEqual(gap, 0)
                        self.assertFalse(viewer.is_modified)
                        self.assertEqual(viewer.markdown_text(), source)
            viewer.deleteLater()

    def test_inline_image_does_not_push_next_line_down_by_its_height(self):
        self.editor.setMarkdown('Before ![Large|400](large.png) ' + 'Following text ' * 20 + '\n\nTail')
        qt.QApplication.processEvents()
        document = self.editor.document()
        block = document.begin()
        self.assertGreater(block.layout().lineCount(), 1)
        first = block.layout().lineAt(0)
        following = block.layout().lineAt(1)
        self.assertGreater(first.height(), 190)
        self.assertLessEqual(following.y() - first.y() - first.height(), 20)
        # Ordinary paragraphs retain their proportional prose spacing.
        self.assertEqual(block.next().blockFormat().lineHeight(), 145)
