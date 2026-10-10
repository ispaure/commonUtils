"""Markdown rendering, local link history, failures and browser activation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch

from commonUtils.fileTypes.registry import file_from_path
from commonUtils.fileTypes.markdownType import MarkdownFile
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer, open_markdown, _windows
from commonUtils.ui.file_browser import FileBrowser


class MarkdownTests(QtTestCase):
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
        self.viewer = MarkdownViewer(self.first, allow_edit=True)
        self.viewer.set_editing(False)
        self.viewer.set_edit_mode('source')
        self.viewer.resize(600, 400)
        self.viewer.show()
        self.addCleanup(self.viewer.deleteLater)
        self.app.processEvents()

    def test_edit_read_icons_and_speech_action_visibility(self):
        viewer = MarkdownViewer(allow_edit=True)
        viewer.set_editing(False)
        self.addCleanup(viewer.deleteLater)
        viewer.show()
        self.assertFalse(viewer.edit_button.icon().isNull())
        self.assertEqual(viewer.edit_button.toolButtonStyle(), qt.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.assertTrue(viewer.speech.action.isVisible())
        viewer.set_editing(True)
        self.assertEqual(viewer.edit_button.accessibleName(), 'Read Markdown')
        self.assertFalse(viewer.speech.action.isVisible())
        self.assertFalse(viewer.speech.anchor.isVisible())
        viewer.set_editing(False)
        self.assertEqual(viewer.edit_button.accessibleName(), 'Edit Markdown')
        self.assertTrue(viewer.speech.action.isVisible())
        self.assertTrue(viewer.speech.anchor.isVisible())

    def test_long_document_and_html_block_keep_tail_in_reading_and_editing(self):
        text = '# Long\n\n' + 'Paragraph text.\n\n' * 3000 + '<div>\nText\n\nTAIL_SENTINEL'
        self.first.write_text(text)
        self.viewer.open_document(self.first)
        self.viewer.set_editing(False)
        self.app.processEvents()
        self.assertIn('TAIL_SENTINEL', self.viewer.browser.toPlainText())
        doc = self.viewer.browser.document()
        doc.documentLayout().documentSize()
        bar = self.viewer.browser.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.app.processEvents()
        bar.setValue(bar.maximum())
        tail = doc.find('TAIL_SENTINEL')
        self.assertTrue(self.viewer.browser.viewport().rect().intersects(self.viewer.browser.cursorRect(tail)))
        self.viewer.set_edit_mode('formatted')
        self.viewer.set_editing(True)
        self.app.processEvents()
        self.assertIn('TAIL_SENTINEL', self.viewer.formatted_editor.toPlainText())
        self.viewer.set_edit_mode('source')
        self.assertIn('TAIL_SENTINEL', self.viewer.editor.toPlainText())
        for editor in (self.viewer.formatted_editor, self.viewer.editor):
            self.viewer.set_edit_mode('formatted' if editor is self.viewer.formatted_editor else 'source')
            tail = editor.document().find('TAIL_SENTINEL')
            editor.setTextCursor(tail)
            editor.ensureCursorVisible()
            self.app.processEvents()
            self.assertTrue(editor.viewport().rect().intersects(editor.cursorRect(tail)))

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

    def test_native_navigation_and_contents_include_nested_duplicate_headings(self):
        self.assertIsInstance(self.viewer.back_button, qt.QToolButton)
        self.assertFalse(self.viewer.back_button.icon().isNull())
        self.viewer.open_document(self.second)
        self.viewer.show_contents()
        popup = self.viewer.toc_popup
        self.assertTrue(popup.windowFlags() & qt.Qt.WindowType.Popup)
        listing = popup.findChild(qt.QListWidget)
        self.assertEqual([listing.item(i).text() for i in range(listing.count())],
                         ['Second', '    Details', '    Details'])
        self.assertEqual(listing.item(2).data(qt.Qt.ItemDataRole.UserRole), 'details-1')
        from PySide6.QtTest import QTest
        QTest.keyClick(listing, qt.Qt.Key.Key_Escape)
        self.assertFalse(popup.isVisible())
        self.viewer.show_contents()
        popup = self.viewer.toc_popup
        listing = popup.findChild(qt.QListWidget)
        self.viewer._select_heading(listing.item(2))
        self.assertFalse(popup.isVisible())
        self.assertEqual(self.viewer.current_path, self.second.resolve())

    def test_edit_preview_and_heading_navigation_preserve_unsaved_source(self):
        self.viewer.set_editing(True)
        self.viewer.editor.appendPlainText('## Unsaved heading\n\nNew text')
        source = self.viewer.editor.toPlainText()
        original = self.first.read_bytes()
        self.assertTrue(self.viewer.is_modified)
        self.viewer.set_editing(False)
        self.assertIn('Unsaved heading', self.viewer.browser.toPlainText())
        self.viewer.show_contents()
        listing = self.viewer.toc_popup.findChild(qt.QListWidget)
        self.viewer._select_heading(listing.item(listing.count() - 1))
        with patch.object(qt.QMessageBox, 'warning') as warning:
            self.viewer.follow_link(qt.QUrl('#unsaved-heading'))
            self.viewer.back()
            warning.assert_not_called()
        self.viewer.set_editing(True)
        self.assertEqual(self.viewer.editor.toPlainText(), source)
        self.assertTrue(self.viewer.is_modified)
        self.assertEqual(self.first.read_bytes(), original)

    def test_save_preserves_bom_crlf_and_failed_replace_keeps_original(self):
        source = b'\xef\xbb\xbf# First\r\n\r\nOriginal\r\n'
        self.first.write_bytes(source)
        self.viewer.open_document(self.first)
        self.viewer.set_editing(True)
        cursor = self.viewer.editor.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        cursor.insertText('Extra')
        with patch('commonUtils.ui.markdown.io.os.replace', side_effect=OSError('blocked')):
            self.assertFalse(self.viewer.save_document())
        self.assertEqual(self.first.read_bytes(), source)
        self.assertTrue(self.viewer.is_modified)
        self.assertEqual(list(self.root.glob('.first.md-*.tmp')), [])
        self.assertTrue(self.viewer.save_document())
        saved = self.first.read_bytes()
        self.assertTrue(saved.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\n', saved.replace(b'\r\n', b''))
        self.assertIn(b'Extra', saved)
        self.assertFalse(self.viewer.is_modified)

    def test_disk_conflict_refuses_overwrite_and_save_as_changes_link_base(self):
        self.viewer.set_editing(True)
        self.viewer.editor.appendPlainText('My changes')
        self.first.write_text('External changes', encoding='utf-8')
        self.assertFalse(self.viewer.save_document())
        self.assertEqual(self.first.read_text(), 'External changes')
        self.assertTrue(self.viewer.is_modified)
        directory = self.root / 'new'
        directory.mkdir()
        destination = directory / 'saved.md'
        self.assertTrue(self.viewer.save_document(destination))
        self.assertEqual(self.viewer.current_path, destination)
        self.assertEqual(Path(self.viewer.browser.document().baseUrl().toLocalFile()), directory)
        self.assertIn('My changes', destination.read_text())

    def test_unsaved_navigation_cancel_discard_and_failed_save(self):
        self.viewer.set_editing(True)
        self.viewer.editor.appendPlainText('Unsaved')
        before = self.viewer.editor.toPlainText()
        buttons = qt.QMessageBox.StandardButton
        with patch.object(qt.QMessageBox, 'warning', return_value=buttons.Cancel):
            self.assertFalse(self.viewer.open_document(self.second))
        self.assertEqual(self.viewer.current_path, self.first.resolve())
        self.assertEqual(self.viewer.editor.toPlainText(), before)
        with patch.object(qt.QMessageBox, 'warning', return_value=buttons.Save), \
                patch.object(self.viewer, 'save_document', return_value=False):
            self.assertFalse(self.viewer.open_document(self.second))
        self.assertEqual(self.viewer.editor.toPlainText(), before)
        with patch.object(qt.QMessageBox, 'warning', return_value=buttons.Discard):
            self.assertTrue(self.viewer.open_document(self.second))
        self.assertFalse(self.viewer.is_modified)
        self.assertNotIn('Unsaved', self.first.read_text())

    def test_save_and_open_actions_shortcuts_and_window_close_cancel(self):
        window = open_markdown(self.first, allow_edit=True)
        self.addCleanup(window.deleteLater)
        viewer = window.viewer
        viewer.set_edit_mode('source')
        self.assertFalse(viewer.location.isVisible())
        self.assertEqual([action.text() for action in window.menuBar().actions()], ['File', 'Edit', 'View'])
        self.assertIn('Ctrl+S', [key.toString() for key in viewer.save_action.shortcuts()])
        self.assertIn('Ctrl+O', [key.toString() for key in viewer.open_action.shortcuts()])
        viewer.set_editing(True)
        viewer.editor.appendPlainText('Saved by action')
        viewer.save_action.trigger()
        self.assertIn('Saved by action', self.first.read_text())
        with patch.object(qt.QFileDialog, 'getOpenFileName', return_value=(str(self.second), '')):
            viewer.open_action.trigger()
        self.assertEqual(viewer.current_path, self.second.resolve())
        viewer.editor.appendPlainText('Unsaved close')
        with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
            self.assertFalse(window.close())
        self.assertTrue(window.isVisible())
        with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard):
            window.close()

    def test_formatting_replace_all_and_undo_are_source_operations(self):
        self.viewer.set_editing(True)
        self.viewer.editor.setPlainText('one one')
        self.viewer.editor.selectAll()
        self.viewer.wrap_selection('**', 'text')
        self.assertEqual(self.viewer.editor.toPlainText(), '**one one**')
        self.viewer.undo_action.trigger()
        self.assertEqual(self.viewer.editor.toPlainText(), 'one one')
        self.viewer.find_text.setText('one')
        self.viewer.replace_text.setText('one plus')
        self.viewer.replace_all()
        self.assertEqual(self.viewer.editor.toPlainText(), 'one plus one plus')
        self.viewer.undo_action.trigger()
        self.assertEqual(self.viewer.editor.toPlainText(), 'one one')
        self.viewer.set_editing(False)
        self.assertFalse(self.viewer.undo_action.isEnabled())
        self.viewer.replace_all()
        self.assertEqual(self.viewer.editor.toPlainText(), 'one one')

    def test_new_document_save_dialog_and_keyboard_save(self):
        from PySide6.QtTest import QTest
        self.viewer.new_action.trigger()
        self.assertIsNone(self.viewer.current_path)
        self.assertTrue(self.viewer.edit_button.isChecked())
        self.viewer.editor.insertPlainText('# New document\n\nText')
        self.viewer.set_editing(False)
        self.assertIn('New document', self.viewer.browser.toPlainText())
        path = self.root / 'created.md'
        with patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            self.viewer.save_action.trigger()
        self.assertEqual(path.read_text(), '# New document\n\nText')
        self.viewer.set_editing(True)
        self.viewer.editor.appendPlainText('Shortcut saved')
        self.viewer.activateWindow()
        self.viewer.editor.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.viewer.editor, qt.Qt.Key.Key_S, qt.Qt.KeyboardModifier.ControlModifier)
        self.app.processEvents()
        self.assertIn('Shortcut saved', path.read_text())
        self.assertFalse(self.viewer.is_modified)

    def test_formatted_edit_default_rendering_noop_save_preserves_exact_source(self):
        window = open_markdown(self.first, allow_edit=True)
        viewer = window.viewer
        self.addCleanup(window.deleteLater)
        original = self.first.read_bytes()
        viewer.set_editing(True)
        self.assertIs(viewer.pages.currentWidget(), viewer.formatted_editor)
        self.assertEqual(viewer.formatted_editor.document().begin().blockFormat().headingLevel(), 1)
        self.assertIn('<table', viewer.formatted_editor.document().toHtml())
        self.assertFalse(viewer.is_modified)
        viewer.set_edit_mode('source')
        self.assertEqual(viewer.editor.toPlainText(), original.decode().replace("\r\n", "\n"))
        viewer.set_edit_mode('formatted')
        self.assertTrue(viewer.save_document())
        self.assertEqual(self.first.read_bytes(), original)
        window.close()

    def test_formatted_text_edit_save_and_source_mode_switch(self):
        self.viewer.set_edit_mode('formatted')
        self.viewer.set_editing(True)
        cursor = self.viewer.formatted_editor.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        cursor.insertText('Formatted new text')
        self.assertTrue(self.viewer.is_modified)
        self.viewer.set_edit_mode('source')
        self.assertIn('Formatted new text', self.viewer.editor.toPlainText())
        self.assertTrue(self.viewer.is_modified)
        self.viewer.editor.appendPlainText('## Source heading')
        self.viewer.set_edit_mode('formatted')
        self.assertIn('Source heading', self.viewer.formatted_editor.toPlainText())
        self.assertTrue(self.viewer.save_document())
        self.assertIn('Formatted new text', self.first.read_text())
        self.assertIn('## Source heading', self.first.read_text())
        self.assertFalse(self.viewer.is_modified)

    def test_formatted_undo_to_original_keeps_exact_bytes(self):
        self.viewer.set_edit_mode('formatted')
        self.viewer.set_editing(True)
        original = self.first.read_bytes()
        self.viewer.formatted_editor.insertPlainText('Changed')
        self.assertTrue(self.viewer.is_modified)
        self.viewer.undo_action.trigger()
        self.assertFalse(self.viewer.is_modified)
        self.assertTrue(self.viewer.save_document())
        self.assertEqual(self.first.read_bytes(), original)

    def test_formatted_formatting_lists_links_and_tables_save_as_markdown(self):
        self.viewer.set_edit_mode('formatted')
        self.viewer.set_editing(True)
        widget = self.viewer.formatted_editor
        widget.setMarkdown('Paragraph\n\n| A | B |\n| --- | --- |\n| One | Two |\n')
        cursor = widget.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.Start)
        cursor.movePosition(qt.QTextCursor.MoveOperation.EndOfBlock, qt.QTextCursor.MoveMode.KeepAnchor)
        widget.setTextCursor(cursor)
        self.viewer.bold_action.trigger()
        self.assertIn('**Paragraph**', widget.document().toMarkdown())
        self.viewer.prefix_lines('## ')
        self.assertEqual(widget.document().begin().blockFormat().headingLevel(), 2)
        self.viewer.prefix_lines('> ')
        with patch.object(qt.QInputDialog, 'getText', return_value=('second%20page.MD', True)):
            self.viewer.insert_link()
        self.assertIn('second%20page.MD', widget.document().toMarkdown())
        self.viewer.find_text.setText('One')
        self.viewer.replace_text.setText('Edited cell')
        self.viewer.replace_all()
        self.assertIn('Edited cell', widget.toPlainText())
        self.assertTrue(self.viewer.save_document())
        self.assertIn('|', self.first.read_text())
        self.assertIn('Edited cell', self.first.read_text())
        self.assertIn('## ', self.first.read_text())

    def test_formatted_cancel_and_failed_save_keep_edits(self):
        self.viewer.set_edit_mode('formatted')
        self.viewer.set_editing(True)
        self.viewer.formatted_editor.insertPlainText('Unsaved rich text')
        original = self.first.read_bytes()
        with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.viewer.open_document(self.second))
        self.assertIn('Unsaved rich text', self.viewer.formatted_editor.toPlainText())
        with patch('commonUtils.ui.markdown.io.os.replace', side_effect=OSError('blocked')):
            self.assertFalse(self.viewer.save_document())
        self.assertTrue(self.viewer.is_modified)
        self.assertEqual(self.first.read_bytes(), original)
        self.viewer.set_editing(False)
        self.assertIn('Unsaved rich text', self.viewer.browser.toPlainText())

    def test_formatted_contents_jump_keeps_edit_mode_and_unsaved_changes(self):
        self.viewer.set_edit_mode('formatted')
        self.viewer.set_editing(True)
        self.viewer.formatted_editor.insertPlainText('Edited ')
        self.viewer.show_contents()
        listing = self.viewer.toc_popup.findChild(qt.QListWidget)
        self.viewer._select_heading(listing.item(0))
        self.assertTrue(self.viewer.edit_button.isChecked())
        self.assertIs(self.viewer.pages.currentWidget(), self.viewer.formatted_editor)
        self.assertTrue(self.viewer.is_modified)
        self.assertEqual(self.viewer.formatted_editor.textCursor().block().blockFormat().headingLevel(), 1)
        self.viewer.prefix_lines('')
        self.assertEqual(self.viewer.formatted_editor.document().begin().blockFormat().headingLevel(), 0)

    def test_heading_anchors_avoid_literal_suffix_collisions_in_both_views(self):
        self.first.write_text('# Foo\n\n## Foo\n\n## Foo-1\n\n## Foo\n', encoding='utf-8')
        self.viewer.open_document(self.first)
        self.assertEqual([anchor for _, _, anchor in self.viewer.headings],
                         ['foo', 'foo-1', 'foo-1-1', 'foo-2'])
        self.viewer.set_edit_mode('formatted')
        self.viewer.set_editing(True)
        self.viewer.show_contents()
        listing = self.viewer.toc_popup.findChild(qt.QListWidget)
        self.viewer._select_heading(listing.item(2))
        self.assertEqual(self.viewer.formatted_editor.textCursor().block().text(), '## Foo-1')
        self.viewer._scroll_formatted_heading('foo-2')
        self.assertEqual(self.viewer.formatted_editor.textCursor().block().text(), '## Foo')
        self.assertGreater(self.viewer.formatted_editor.textCursor().position(), 10)

    def test_live_typed_markup_saves_with_yaml_and_updates_contents(self):
        from PySide6.QtTest import QTest
        self.first.write_text('---\ntitle: Preserved\n---\n\nParagraph\n', encoding='utf-8')
        self.viewer.open_document(self.first)
        self.viewer.set_edit_mode('formatted')
        self.viewer.set_editing(True)
        widget = self.viewer.formatted_editor
        cursor = widget.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        widget.setTextCursor(cursor)
        QTest.keyClicks(widget, '## Typed heading')
        QTest.keyClick(widget, qt.Qt.Key.Key_Return)
        QTest.keyClicks(widget, 'A **bold** word')
        self.assertEqual(widget.textCursor().block().blockFormat().headingLevel(), 0)
        self.assertTrue(self.viewer.is_modified)
        self.viewer.show_contents()
        self.assertIn('Typed heading', [title for _, title, _ in self.viewer.headings])
        self.assertTrue(self.viewer.save_document())
        saved = self.first.read_text()
        self.assertTrue(saved.startswith('---\ntitle: Preserved\n---\n'))
        self.assertIn('## Typed heading', saved)
        self.assertIn('**bold**', saved)
        self.assertFalse(self.viewer.is_modified)

    def test_live_preview_navigation_is_noop_and_fenced_code_save_preserves_yaml(self):
        from PySide6.QtTest import QTest
        self.first.write_text('---\ntitle: Kept\n---\n\nBefore **obsidian** after\n', encoding='utf-8')
        viewer = MarkdownViewer(self.first, allow_edit=True)
        self.addCleanup(viewer.deleteLater)
        original = self.first.read_bytes()
        cursor = viewer.formatted_editor.document().find('obsidian')
        cursor.setPosition(cursor.selectionStart() + 3)
        viewer.formatted_editor.setTextCursor(cursor)
        self.assertFalse(viewer.is_modified)
        self.assertTrue(viewer.save_document())
        self.assertEqual(self.first.read_bytes(), original)
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        viewer.formatted_editor.setTextCursor(cursor)
        QTest.keyClicks(viewer.formatted_editor, '```python')
        QTest.keyClick(viewer.formatted_editor, qt.Qt.Key.Key_Return)
        QTest.keyClicks(viewer.formatted_editor, 'print("hello")')
        QTest.keyClick(viewer.formatted_editor, qt.Qt.Key.Key_Return)
        QTest.keyClicks(viewer.formatted_editor, '```')
        self.assertTrue(viewer.save_document())
        self.assertTrue(self.first.read_text().startswith('---\ntitle: Kept\n---\n'))
        self.assertIn('```python\nprint("hello")\n```', self.first.read_text())

    def test_default_preview_has_no_editing_controls_or_write_actions(self):
        window = open_markdown(self.first)
        self.addCleanup(window.deleteLater)
        viewer = window.viewer
        self.assertFalse(viewer.allow_edit)
        self.assertTrue(viewer.edit_button.isHidden())
        self.assertFalse(viewer.edit_button.isEnabled())
        self.assertTrue(viewer.editor.isReadOnly())
        self.assertTrue(viewer.formatted_editor.isReadOnly())
        visible_file = [action.text() for action in window._file_menu.actions() if action.isVisible()]
        self.assertNotIn('New', visible_file)
        self.assertNotIn('Save', visible_file)
        self.assertNotIn('Save As…', visible_file)
        self.assertNotIn('Edit / Read', [action.text() for action in window._view_menu.actions()])
        self.assertEqual(viewer.find_action.text(), 'Find…')
        viewer.show_find()
        self.assertTrue(viewer.replace_text.isHidden())
        for action in (viewer.new_action, viewer.save_action, viewer.save_as_action):
            self.assertFalse(action.isEnabled())
        viewer.set_editing(True)
        viewer.edit_button.setChecked(True)
        self.assertFalse(viewer.edit_button.isChecked())
        self.assertIs(viewer.pages.currentWidget(), viewer.browser)
        original = self.first.read_bytes()
        destination = self.root / 'copy.md'
        self.assertFalse(viewer.new_document())
        self.assertFalse(viewer.save_document())
        self.assertFalse(viewer.save_document(destination))
        with patch.object(qt.QFileDialog, 'getSaveFileName') as dialog:
            self.assertFalse(viewer.save_as_dialog())
        dialog.assert_not_called()
        self.assertEqual(self.first.read_bytes(), original)
        self.assertFalse(destination.exists())

    def test_default_preview_navigation_preserves_reading_only_mode(self):
        viewer = MarkdownViewer(self.first)
        self.addCleanup(viewer.deleteLater)
        viewer.follow_link(qt.QUrl('second%20page.MD#details'))
        self.assertEqual(viewer.current_path, self.second.resolve())
        viewer.back()
        self.assertEqual(viewer.current_path, self.first.resolve())
        viewer.forward()
        self.assertEqual(viewer.current_path, self.second.resolve())
        self.assertFalse(viewer.allow_edit)
        self.assertTrue(viewer.edit_button.isHidden())
        viewer.find_text.setText('Details')
        self.assertTrue(viewer.find_next())
        self.assertFalse(viewer.is_modified)

    def test_editable_widget_defaults_active_and_keeps_open_failures_visible(self):
        viewer = MarkdownViewer(allow_edit=True)
        self.addCleanup(viewer.deleteLater)
        self.assertTrue(viewer.edit_button.isChecked())
        self.assertIs(viewer.pages.currentWidget(), viewer.formatted_editor)
        self.assertFalse(viewer.is_modified)
        failed = MarkdownViewer(self.root / 'missing.md', allow_edit=True)
        self.addCleanup(failed.deleteLater)
        self.assertTrue(failed.edit_button.isChecked())
        self.assertIn('Cannot open', failed.status.text())

    def test_explicit_edit_permission_survives_link_navigation(self):
        window = open_markdown(self.first, allow_edit=True)
        self.addCleanup(window.deleteLater)
        viewer = window.viewer
        self.assertTrue(viewer.allow_edit)
        self.assertFalse(viewer.edit_button.isHidden())
        self.assertTrue(viewer.edit_button.isChecked())
        self.assertIs(viewer.pages.currentWidget(), viewer.formatted_editor)
        viewer.follow_link(qt.QUrl('second%20page.MD'))
        viewer.set_edit_mode('source')
        viewer.set_editing(True)
        viewer.editor.appendPlainText('Explicitly edited')
        self.assertTrue(viewer.save_document())
        self.assertIn('Explicitly edited', self.second.read_text())

    def test_window_lifetime_and_browser_markdown_activation(self):
        self.assertIsInstance(file_from_path(self.second), MarkdownFile)
        self.assertIsInstance(file_from_path('missing.markdown'), MarkdownFile)
        window = open_markdown(self.first, allow_edit=True)
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
        opened.assert_called_once_with(self.second, parent=browser.window(), allow_edit=True)
