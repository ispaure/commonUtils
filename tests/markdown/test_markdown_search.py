"""Desktop search scopes, transient marks and wiki pane geometry."""
from pathlib import Path
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer


class MarkdownSearchTests(QtTestCase):
    def make_viewer(self, root, *, editing=False):
        path = Path(root) / 'index.md'
        path.write_text('# Library\n\nNeedle first. Needle second.\n', encoding='utf-8')
        other = Path(root) / 'other.md'
        other.write_text('# Other\n\nAnother needle.\n', encoding='utf-8')
        viewer = MarkdownViewer(path, directory=root, allow_edit=editing)
        viewer.resize(1000, 700)
        viewer.show()
        qt.QApplication.instance().processEvents()
        return viewer, other.resolve()

    def test_idle_alignment_and_scoped_search(self):
        with self.temporary_directory() as root:
            viewer, other = self.make_viewer(root)
            self.assertTrue(viewer.wiki.mode.isHidden())
            self.assertTrue(viewer.wiki.notice.isHidden())
            def bottom(widget):
                return widget.mapTo(viewer, widget.rect().bottomLeft()).y()
            self.assertEqual(bottom(viewer.wiki.tree), bottom(viewer.pages))
            viewer.wiki.mode.setCurrentIndex(1)
            viewer.wiki.search.setText('needle')
            viewer.wiki.populate()
            self.assertFalse(viewer.wiki.mode.isHidden())
            self.assertEqual(len(viewer.browser.extraSelections()), 2)
            iterator = qt.QTreeWidgetItemIterator(viewer.wiki.tree)
            while iterator.value() and iterator.value().data(0, qt.Qt.ItemDataRole.UserRole) != other:
                iterator += 1
            self.assertIsNotNone(iterator.value())
            viewer.wiki.open_item(iterator.value())
            self.assertEqual(viewer.browser.textCursor().selectedText().lower(), 'needle')
            viewer.show_find()
            viewer.find_text.setText('Another')
            self.assertEqual(viewer.find_count.text(), '1 match')
            self.assertEqual(len(viewer.browser.extraSelections()), 2)
            viewer.close_find()
            self.assertEqual(len(viewer.browser.extraSelections()), 1)
            viewer.wiki.search.clear()
            self.assertEqual(len(viewer.browser.extraSelections()), 0)
            self.assertTrue(viewer.wiki.mode.isHidden())
            self.assertFalse(viewer.is_modified)

    def test_find_wraps_and_marks_survive_render_without_dirtying(self):
        with self.temporary_directory() as root:
            viewer, _ = self.make_viewer(root, editing=True)
            viewer.set_edit_mode('source')
            viewer.show_find()
            viewer.find_text.setText('needle')
            self.assertEqual(viewer.find_count.text(), '2 matches')
            self.assertEqual(len(viewer.editor.extraSelections()), 2)
            first = viewer.editor.textCursor().selectionStart()
            self.assertTrue(viewer.find_next())
            self.assertGreater(viewer.editor.textCursor().selectionStart(), first)
            self.assertTrue(viewer.find_next())
            self.assertEqual(viewer.editor.textCursor().selectionStart(), first)
            self.assertTrue(viewer.find_previous())
            self.assertGreater(viewer.editor.textCursor().selectionStart(), first)
            viewer.set_editing(False)
            viewer._refresh_search_highlights()
            self.assertEqual(len(viewer.editor.extraSelections()), 0)
            self.assertEqual(len(viewer.browser.extraSelections()), 2)
            viewer._render_source(viewer.markdown_text())
            self.wait_until(lambda: len(viewer.browser.extraSelections()) == 2)
            self.assertFalse(viewer.is_modified)
            viewer.find_text.setText('absent')
            self.assertEqual(viewer.find_count.text(), '0 matches')
            self.assertFalse(viewer.find_next())

    def test_clear_search_releases_its_selection_but_preserves_other_marks(self):
        with self.temporary_directory() as root:
            viewer, _ = self.make_viewer(root)
            viewer.show_find()
            viewer.find_text.setText('needle')
            self.assertTrue(viewer.browser.textCursor().hasSelection())
            other = qt.QTextEdit.ExtraSelection()
            other.cursor = viewer.browser.textCursor()
            other.format.setProperty(qt.QTextFormat.Property.UserProperty + 77, True)
            viewer.browser.setExtraSelections(viewer.browser.extraSelections() + [other])
            viewer.close_find()
            self.assertFalse(viewer.browser.textCursor().hasSelection())
            self.assertEqual(len(viewer.browser.extraSelections()), 1)
            viewer.wiki.search.setText('needle')
            viewer._reveal_library_match()
            self.assertTrue(viewer.browser.textCursor().hasSelection())
            viewer.wiki.search.clear()
            self.assertFalse(viewer.browser.textCursor().hasSelection())
            self.assertEqual(len(viewer.browser.extraSelections()), 1)
            viewer.show_find()
            viewer.find_text.setText('needle')
            cursor = viewer.browser.textCursor()
            cursor.select(qt.QTextCursor.SelectionType.BlockUnderCursor)
            viewer.browser.setTextCursor(cursor)
            viewer.close_find()
            self.assertTrue(viewer.browser.textCursor().hasSelection())

    def test_search_fits_a_narrow_document_pane(self):
        with self.temporary_directory() as root:
            viewer, _ = self.make_viewer(root)
            viewer.resize(700, 500)
            viewer.show_find()
            viewer.find_text.setText('needle')
            qt.QApplication.instance().processEvents()
            self.assertLessEqual(viewer.minimumSizeHint().width(), 700)
            self.assertLessEqual(viewer.find_bar.geometry().right(), viewer.document_panel.width())
            self.assertFalse(viewer.is_modified)
