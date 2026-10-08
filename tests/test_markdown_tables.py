"""Table structure editing, undo, Markdown publication and preview boundaries."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer


class MarkdownTableTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'table.md'
        self.path.write_text('---\ntitle: Kept\n---\n\nBefore\n\n| A | B |\n| --- | --- |\n| one | two |\n\nAfter\n')
        self.viewer = MarkdownViewer(self.path, allow_edit=True)
        self.addCleanup(self.viewer.deleteLater)
        self.viewer.set_editing(True)
        self.editor = self.viewer.formatted_editor
        self.table = next(frame for frame in self.editor.document().rootFrame().childFrames()
                          if isinstance(frame, qt.QTextTable))
        self.editor.setTextCursor(self.table.cellAt(1, 0).firstCursorPosition())

    def test_row_column_edits_keep_other_cells_and_undo_as_single_operations(self):
        self.assertTrue(self.viewer._edit_table('row_below'))
        self.assertEqual(self.table.rows(), 3)
        self.assertTrue(self.viewer._edit_table('column_after'))
        self.assertEqual(self.table.columns(), 3)
        self.assertIn('one', self.editor.toPlainText())
        self.assertIn('two', self.editor.toPlainText())
        self.editor.undo()
        self.assertEqual(self.table.columns(), 2)
        self.editor.undo()
        self.assertEqual(self.table.rows(), 2)
        self.editor.redo()
        self.assertEqual(self.table.rows(), 3)
        self.assertTrue(self.viewer._edit_table('delete_row'))
        self.assertEqual(self.table.rows(), 2)
        self.assertTrue(self.viewer._edit_table('column_before'))
        self.assertEqual(self.table.columns(), 3)
        self.assertTrue(self.viewer._edit_table('delete_column'))
        self.assertEqual(self.table.columns(), 2)
        self.assertIn('Before', self.editor.toPlainText())
        self.assertIn('After', self.editor.toPlainText())

    def test_actions_follow_cell_mode_and_preview_permission(self):
        self.assertTrue(self.viewer._table_actions['row_above'].isEnabled())
        self.viewer.set_edit_mode('source')
        self.assertFalse(self.viewer._edit_table('delete_row'))
        self.viewer.set_edit_mode('formatted')
        cursor = self.editor.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)
        self.assertFalse(self.viewer._edit_table('delete_column'))
        self.assertTrue(self.viewer.table_insert_action.isEnabled())
        self.viewer.set_editing(False)
        self.assertFalse(self.viewer.table_insert_action.isEnabled())
        preview = MarkdownViewer(self.path)
        self.addCleanup(preview.deleteLater)
        self.assertFalse(preview._edit_table('delete_row'))
        self.assertFalse(preview._insert_table_dialog())

    def test_insert_and_delete_whole_table_preserves_neighbors_and_saves_yaml(self):
        self.assertTrue(self.viewer._edit_table('delete_table'))
        self.assertNotIn('one', self.editor.toPlainText())
        self.assertIn('Before', self.editor.toPlainText())
        self.assertIn('After', self.editor.toPlainText())
        cursor = self.editor.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        self.editor.setTextCursor(cursor)
        with patch.object(qt.QInputDialog, 'getInt', side_effect=[(2, True), (3, True)]):
            self.assertTrue(self.viewer._insert_table_dialog())
        table = self.editor.textCursor().currentTable()
        self.assertEqual((table.rows(), table.columns()), (2, 3))
        self.editor.insertPlainText('Header')
        self.editor.setTextCursor(table.cellAt(1, 0).firstCursorPosition())
        self.editor.insertPlainText('Cell')
        self.assertTrue(self.viewer.save_document())
        saved = self.path.read_text()
        self.assertTrue(saved.startswith('---\ntitle: Kept\n---\n'))
        self.assertIn('|', saved)
        self.assertIn('Header', saved)
        self.assertIn('Cell', saved)

    def test_cancel_insert_and_delete_last_column_are_safe(self):
        before = self.editor.document().toMarkdown()
        cursor = self.editor.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)
        with patch.object(qt.QInputDialog, 'getInt', return_value=(0, False)):
            self.assertFalse(self.viewer._insert_table_dialog())
        self.assertEqual(before, self.editor.document().toMarkdown())
        self.editor.setTextCursor(self.table.cellAt(0, 1).firstCursorPosition())
        self.assertTrue(self.viewer._edit_table('delete_column'))
        self.assertEqual(self.table.columns(), 1)
        self.assertTrue(self.viewer._edit_table('delete_column'))
        self.assertIsNone(self.editor.textCursor().currentTable())
        self.assertIn('Before', self.editor.toPlainText())
