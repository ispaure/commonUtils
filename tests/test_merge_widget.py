import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.text_merge import merge_text
from commonUtils.ui.code_editor.merge import MergeDialog, MergeWidget
from commonUtils.ui.code_editor.diff import DiffDialog, compare_text, apply_change


class MergeWidgetTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=qt.QApplication.instance() or qt.QApplication([])

    def test_resolution_manual_edit_undo_redo_and_apply_gate(self):
        apply=Mock()
        dialog=MergeDialog(merge_text('a\nb\n', 'a\n😀 left\n', 'a\nright\n'), apply=apply)
        dialog.show(); self.app.processEvents()
        self.assertFalse(dialog.apply_button.isEnabled())
        widget=dialog.widget; widget.choose(0, 'left')
        self.assertEqual(widget.result.toPlainText(), 'a\n😀 left\n')
        self.assertTrue(dialog.apply_button.isEnabled())
        widget.undo(); self.assertFalse(dialog.apply_button.isEnabled())
        widget.redo(); self.assertTrue(dialog.apply_button.isEnabled())
        cursor=widget.result.textCursor(); cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        cursor.insertText('manual\n'); widget.mark_manual()
        widget.undo(); widget.undo(); self.assertEqual(widget.result.toPlainText(), 'a\n😀 left\n')
        dialog.apply_result(); apply.assert_called_once_with('a\n😀 left\n')

    def test_two_way_accepts_multiple_changes_and_rejects_stale_buffer(self):
        current=['a\nb\nc\n']
        def apply(model,index):
            start,end,value=apply_change(model,index,current[0])
            current[0]=current[0][:start]+value+current[0][end:]
            return current[0]
        dialog=DiffDialog(compare_text('left\nb\nright\n', current[0]), apply=apply)
        dialog.show(); self.app.processEvents()
        dialog.apply_current(); self.assertEqual(len(dialog.model.changes), 1)
        dialog.apply_current(); self.assertEqual(current[0], 'left\nb\nright\n')
        self.assertFalse(dialog.use_left.isEnabled())
        dialog.close()
        dialog=DiffDialog(compare_text('left', 'right'), apply=apply)
        dialog.apply_current(); self.assertIn('buffer changed',dialog.status.text())

    def test_bridge_arrow_and_linked_scrolling_keep_original_texts(self):
        widget=MergeWidget(merge_text('a\nb\nc\n', 'x\ny\na\nb\nc\n', 'a\nb\nright\n'))
        widget.resize(1200,700); widget.show(); self.app.processEvents()
        widget.left_bridge.picked.emit(0)
        self.assertTrue(widget.session.text.startswith('x\ny\n'))
        self.assertEqual(widget.editors[0].toPlainText(), widget.session.model.left)
        widget.grab(); widget.close()
