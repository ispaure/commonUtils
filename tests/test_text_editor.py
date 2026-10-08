"""Plain-text saves preserve file conventions and refuse to overwrite external edits."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from commonUtils.ui.text_editor import TextFileEditor


class TextEditorTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'config.ini'
        self.path.write_bytes(b'\xef\xbb\xbf[Section]\r\nkey=value\r\n')
        self.editor = TextFileEditor(self.path)
        self.addCleanup(self.editor.deleteLater)

    def edit(self):
        self.editor.text.moveCursor(qt.QTextCursor.MoveOperation.End)
        self.editor.text.insertPlainText('other=new\n')

    def test_atomic_save_preserves_bom_crlf_and_exact_text(self):
        self.edit()
        self.assertTrue(self.editor.is_modified)
        self.assertTrue(self.editor.save())
        self.assertEqual(self.path.read_bytes(), b'\xef\xbb\xbf[Section]\r\nkey=value\r\nother=new\r\n')
        self.assertFalse(self.editor.is_modified)

    def test_external_changes_are_preserved_on_save(self):
        self.edit()
        self.path.write_text('externally changed')
        self.assertFalse(self.editor.save())
        self.assertEqual(self.path.read_text(), 'externally changed')
        self.assertTrue(self.editor.is_modified)
        self.assertIn('changed on disk', self.editor.status.text())

    def test_cancel_preserves_dirty_document_and_save_on_close(self):
        self.edit()
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.editor.can_close())
        self.assertTrue(self.editor.is_modified)
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Save):
            self.assertTrue(self.editor.can_close())
        self.assertIn(b'other=new', self.path.read_bytes())
