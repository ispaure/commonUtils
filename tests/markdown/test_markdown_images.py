"""Animated GIF rendering, editable drops, persistence and decoder lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer

GIF = base64.b64decode(
    'R0lGODlhBAAEAIEAAP8AAAAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQABgAAACwAAAAABAAE'
    'AAAICQABCBxIsCCAgAAh+QQBBgABACwAAAAABAAEAIEAAP8AAAAAAAAAAAAICQABCBxIsCCAgAA7')


class MarkdownImageTests(QtTestCase):
    def setUp(self):
        self.scope = self.temporary_directory()
        self.root = Path(self.scope.name)
        self.image = self.root / 'assets' / 'two colors #1.GIF'
        self.image.parent.mkdir()
        self.image.write_bytes(GIF)
        self.path = self.root / 'page.md'
        self.target = 'assets/two%20colors%20%231.GIF'
        self.path.write_text(f'# GIF\n\n![Colors]({self.target})\n')
        self.viewer = MarkdownViewer(self.path, allow_edit=True)
        self.viewer.resize(600, 400)
        self.viewer.show()

    def assert_animates(self, widget):
        self.wait_until(lambda: bool(widget.animated_images.movies), message='GIF decoder created')
        movie = next(iter(widget.animated_images.movies.values()))[1]
        self.assertEqual(movie.state(), qt.QMovie.MovieState.Running)
        frames = []
        movie.frameChanged.connect(lambda _: frames.append(movie.currentImage().pixelColor(0, 0).name()))
        self.wait_until(lambda: len(set(frames)) == 2, message='both GIF frames displayed')
        self.wait_until(lambda: movie.currentFrameNumber() == 1, message='second GIF frame active')
        resource = widget.document().resource(qt.QTextDocument.ResourceType.ImageResource, qt.QUrl(self.target))
        if isinstance(resource, qt.QPixmap):
            resource = resource.toImage()
        self.assertEqual(resource.pixelColor(0, 0), movie.currentImage().pixelColor(0, 0))
        return movie

    def test_animation_in_both_modes_preserves_source_dirty_and_undo(self):
        source = self.viewer.markdown_text()
        rich = self.viewer.formatted_editor
        before = rich.document().toMarkdown()
        undo = rich.document().isUndoAvailable()
        self.assert_animates(rich)
        self.assertEqual(rich.document().toMarkdown(), before)
        self.assertEqual(rich.document().isUndoAvailable(), undo)
        self.assertFalse(self.viewer.is_modified)
        self.viewer.set_editing(False)
        self.assert_animates(self.viewer.browser)
        self.assertEqual(self.viewer.markdown_text(), source)
        self.assertFalse(self.viewer.is_modified)
        self.assertEqual(next(iter(rich.animated_images.movies.values()))[1].state(), qt.QMovie.MovieState.Paused)

    def test_dropped_gif_round_trips_save_reopen_and_undo(self):
        self.path.write_text('# Drop here\n')
        self.viewer.open_document(self.path)
        editor = self.viewer.formatted_editor
        cursor = editor.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        mime = qt.QMimeData()
        mime.setUrls([qt.QUrl.fromLocalFile(str(self.image))])
        self.assertTrue(editor.canInsertFromMimeData(mime))
        editor.insertFromMimeData(mime)
        self.assert_animates(editor)
        self.assertTrue(self.viewer.is_modified)
        self.assertIn(self.target, editor.document().toMarkdown())
        editor.undo()
        self.wait_until(lambda: not editor.animated_images.movies, message='removed GIF decoder retired')
        editor.redo()
        self.assertTrue(self.viewer.save_document())
        self.assertIn(self.target, self.path.read_text())
        self.viewer.set_editing(False)
        self.assert_animates(self.viewer.browser)
        self.viewer.open_document(self.path)
        self.assert_animates(self.viewer.browser)

    def test_source_drop_inserts_relative_reference(self):
        self.viewer.set_edit_mode('source')
        mime = qt.QMimeData()
        mime.setUrls([qt.QUrl.fromLocalFile(str(self.image))])
        self.viewer.editor.insertFromMimeData(mime)
        self.assertIn(f'![two colors #1]({self.target})', self.viewer.editor.toPlainText())
        self.viewer.set_editing(False)
        self.assert_animates(self.viewer.browser)

    def test_navigation_retires_decoders(self):
        self.assert_animates(self.viewer.formatted_editor)
        other = self.root / 'other.md'
        other.write_text('# No GIF')
        self.viewer.open_document(other)
        self.wait_until(lambda: not self.viewer.formatted_editor.animated_images.movies,
                        message='old page decoder retired')

    def test_provider_loader_is_not_bypassed(self):
        editor = self.viewer.formatted_editor
        editor.document().resource_loader = lambda kind, url: None
        with patch('commonUtils.ui.markdown.images.qt.QMovie') as decoder:
            editor.animated_images.refresh()
            decoder.assert_not_called()
        self.assertFalse(editor.animated_images.movies)

    def test_hidden_surface_pauses_and_resumes(self):
        movie = self.assert_animates(self.viewer.formatted_editor)
        self.viewer.hide()
        self.assertEqual(movie.state(), qt.QMovie.MovieState.Paused)
        self.viewer.show()
        self.assertEqual(movie.state(), qt.QMovie.MovieState.Running)

    def test_file_drag_drop_inserts_at_pointer(self):
        editor = self.viewer.formatted_editor
        qt.QApplication.processEvents()
        mime = qt.QMimeData()
        mime.setUrls([qt.QUrl.fromLocalFile(str(self.image))])
        point = editor.cursorRect(qt.QTextCursor(editor.document())).center()
        enter = qt.QDragEnterEvent(point, qt.Qt.DropAction.CopyAction, mime,
                                  qt.Qt.MouseButton.LeftButton, qt.Qt.KeyboardModifier.NoModifier)
        qt.QApplication.sendEvent(editor.viewport(), enter)
        self.assertTrue(enter.isAccepted())
        drop = qt.QDropEvent(qt.QPointF(point), qt.Qt.DropAction.CopyAction, mime,
                            qt.Qt.MouseButton.LeftButton, qt.Qt.KeyboardModifier.NoModifier)
        qt.QApplication.sendEvent(editor.viewport(), drop)
        self.assertTrue(drop.isAccepted())
        self.assertTrue(editor.document().begin().begin().fragment().charFormat().isImageFormat())
        self.assertIn(self.target, self.viewer.markdown_text())

    def test_base_url_change_rebinds_decoder(self):
        editor = self.viewer.formatted_editor
        old = self.assert_animates(editor)
        moved = self.root / 'new'
        (moved / 'assets').mkdir(parents=True)
        (moved / 'assets' / self.image.name).write_bytes(GIF)
        editor.document().setBaseUrl(qt.QUrl.fromLocalFile(str(moved) + '/'))
        self.wait_until(lambda: editor.animated_images.movies[self.target][1] is not old,
                        message='decoder follows changed document base')
        self.assertEqual(Path(editor.animated_images.movies[self.target][0]), moved / 'assets' / self.image.name)

    def test_unsaved_source_drop_uses_absolute_url(self):
        viewer = MarkdownViewer(allow_edit=True)
        viewer.set_edit_mode('source')
        mime = qt.QMimeData()
        mime.setUrls([qt.QUrl.fromLocalFile(str(self.image))])
        viewer.editor.insertFromMimeData(mime)
        self.assertIn(qt.QUrl.fromLocalFile(str(self.image)).toString(
            qt.QUrl.ComponentFormattingOption.FullyEncoded), viewer.editor.toPlainText())

    def test_protected_local_root_is_not_opened_by_decoder(self):
        from commonUtils.filesystem.local_access import protect_local_root
        editor = self.viewer.formatted_editor
        release = protect_local_root(self, self.root, 'Provider access required')
        try:
            with patch('commonUtils.ui.markdown.images.qt.QMovie') as decoder:
                editor.animated_images.refresh()
                decoder.assert_not_called()
        finally:
            release()

    def test_missing_and_invalid_gifs_do_not_start_decoders_or_dirty_source(self):
        (self.root / 'broken.gif').write_bytes(b'GIF89a truncated')
        source = '![Bad](broken.gif) ![Missing](missing.gif)'
        self.path.write_text(source)
        self.viewer.open_document(self.path)
        qt.QApplication.processEvents()
        self.assertFalse(self.viewer.formatted_editor.animated_images.movies)
        self.assertFalse(self.viewer.is_modified)
        self.assertEqual(self.viewer.markdown_text(), source)
        self.viewer.set_editing(False)
        qt.QApplication.processEvents()
        self.assertFalse(self.viewer.browser.animated_images.movies)
        self.assertFalse(self.viewer.is_modified)

    def test_decoder_error_retires_movie_without_changing_source(self):
        movie = self.assert_animates(self.viewer.formatted_editor)
        source = self.viewer.markdown_text()
        movie.error.emit(qt.QImageReader.ImageReaderError.InvalidDataError)
        self.assertFalse(self.viewer.formatted_editor.animated_images.movies)
        self.assertEqual(movie.state(), qt.QMovie.MovieState.NotRunning)
        self.assertEqual(self.viewer.markdown_text(), source)
        self.assertFalse(self.viewer.is_modified)
