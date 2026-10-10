import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.persistence.merge import merge_text
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

    def key(self, widget, standard):
        from PySide6.QtTest import QTest
        window = widget.window(); window.show(); window.raise_(); window.activateWindow()
        self.assertTrue(QTest.qWaitForWindowActive(window, 2000))
        widget.setFocus(); self.app.processEvents()
        self.assertTrue(widget.hasFocus())
        # Let Cocoa finish updating native shortcut routing after activation.
        QTest.qWait(20)
        QTest.keySequence(widget, qt.QKeySequence(qt.QKeySequence.keyBindings(standard)[0]))
        self.app.processEvents()

    def test_merge_shortcuts_from_result_source_and_toolbar_focus(self):
        widget = MergeWidget(merge_text('base\n', 'left 😀\n', 'right\n'))
        widget.show(); self.app.processEvents()
        for focus in (widget.result, widget.editors[0], widget.editors[2], widget.buttons[0]):
            with self.subTest(focus=focus.accessibleName()):
                widget.choose(0, 'left')
                resolved = widget.session.snapshot()
                self.key(focus, qt.QKeySequence.StandardKey.Undo)
                self.assertEqual(widget.session.text, 'base\n')
                self.assertEqual(widget.session.unresolved, 1)
                self.key(focus, qt.QKeySequence.StandardKey.Redo)
                self.assertEqual(widget.session.snapshot(), resolved)
                widget.undo()

    def test_merge_manual_unicode_selection_paste_delete_and_branch(self):
        widget = MergeWidget(merge_text('😀 base\nkeep\n', '😀 left\nkeep\n', '😀 right\nkeep\n'))
        initial = widget.session.snapshot()
        states = [initial]
        widget.choose(0, 'both'); states.append(widget.session.snapshot())
        cursor = widget.result.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        cursor.insertText('paste 😀\nsecond line\n'); states.append(widget.session.snapshot())
        cursor.setPosition(0); cursor.setPosition(2, qt.QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText(); states.append(widget.session.snapshot())
        widget.mark_manual(); states.append(widget.session.snapshot())
        for expected in reversed(states[:-1]):
            widget.result.undo()
            self.assertEqual(widget.session.snapshot(), expected)
            self.assertEqual(widget.result.toPlainText(), expected[0])
        for expected in states[1:]:
            widget.result.redo()
            self.assertEqual(widget.session.snapshot(), expected)
        widget.undo()
        widget.result.insertPlainText('branch')
        self.assertFalse(widget.session.future)
        before = widget.session.snapshot(); widget.redo()
        self.assertEqual(widget.session.snapshot(), before)
        self.assertFalse(widget.buttons[4].isEnabled())

    def test_merge_nonconflicting_bulk_is_one_step_and_empty_history_is_safe(self):
        widget = MergeWidget(merge_text('a\nb\nc\n', 'left\nb\nc\n', 'a\nb\nright\n'))
        initial = widget.session.snapshot()
        widget.undo(); widget.redo(); self.assertEqual(widget.session.snapshot(), initial)
        widget.apply_nonconflicting(); resolved = widget.session.snapshot()
        self.assertEqual(widget.session.text, 'left\nb\nright\n')
        widget.undo(); self.assertEqual(widget.session.snapshot(), initial)
        widget.redo(); self.assertEqual(widget.session.snapshot(), resolved)
        count = len(widget.session.history)
        widget.apply_nonconflicting(); self.assertEqual(len(widget.session.history), count)

    def test_diff_multiple_hunks_undo_redo_shortcuts_and_branch(self):
        from commonUtils.ui.code_editor.widget import CodeEdit
        editor = CodeEdit(); editor.setPlainText('😀 old\nkeep\nlast')
        def apply(model, index):
            start, end, value = apply_change(model, index, editor.toPlainText())
            cursor = editor.textCursor()
            cursor.setPosition(len(model.right[:start].encode('utf-16-le')) // 2)
            cursor.setPosition(len(model.right[:end].encode('utf-16-le')) // 2, qt.QTextCursor.MoveMode.KeepAnchor)
            cursor.beginEditBlock(); cursor.insertText(value); cursor.endEditBlock()
            return editor.toPlainText()
        def history(action, model):
            if editor.toPlainText() != model.right:
                raise ValueError('stale buffer')
            action(); return editor.toPlainText()
        dialog = DiffDialog(compare_text('😀 new\nkeep\nlast\n', editor.toPlainText()), apply=apply,
                            undo=lambda model: history(editor.undo, model), redo=lambda model: history(editor.redo, model))
        states = [editor.toPlainText()]
        dialog.apply_current(); states.append(editor.toPlainText())
        dialog.apply_current(); states.append(editor.toPlainText())
        self.assertFalse(dialog.use_left.isEnabled())
        for focus, expected in zip((dialog.editors[0], dialog.editors[1]), reversed(states[:-1])):
            self.key(focus, qt.QKeySequence.StandardKey.Undo)
            self.assertEqual(editor.toPlainText(), expected)
            self.assertEqual(dialog.model.right, expected)
        dialog.findChild(qt.QTabWidget).setCurrentIndex(1)
        for expected in states[1:]:
            self.key(dialog.unified, qt.QKeySequence.StandardKey.Redo)
            self.assertEqual(editor.toPlainText(), expected)
            self.assertEqual(dialog.model.right, expected)
        dialog.undo(); dialog.apply_current()
        self.assertFalse(dialog.future)
        self.assertFalse(dialog.history_actions[1].isEnabled())
        unchanged = editor.toPlainText(); dialog.redo(); self.assertEqual(editor.toPlainText(), unchanged)
        editor.insertPlainText('external')
        unchanged = editor.toPlainText(); dialog.undo()
        self.assertEqual(editor.toPlainText(), unchanged)
        self.assertIn('stale', dialog.status.text())

    def test_result_context_menu_routes_live_session_history(self):
        from unittest.mock import patch
        widget = MergeWidget(merge_text('base', 'left', 'right'))
        widget.choose(0, 'left')
        event = qt.QContextMenuEvent(qt.QContextMenuEvent.Reason.Mouse, qt.QPoint(1, 1), qt.QPoint(1, 1))
        def invoke(menu, point):
            actions = {action.text(): action for action in menu.actions()}
            self.assertTrue(actions['Undo merge edit'].isEnabled())
            self.assertFalse(actions['Redo merge edit'].isEnabled())
            self.assertFalse(any('Undo' in text and text != 'Undo merge edit' for text in actions))
            actions['Undo merge edit'].trigger()
        menu = widget.result.createStandardContextMenu()
        menu.exec = lambda point: invoke(menu, point)
        with patch.object(widget.result, 'createStandardContextMenu', return_value=menu):
            widget.result.contextMenuEvent(event)
        self.assertEqual(widget.session.text, 'base')
        def redo(menu, point):
            actions = {action.text(): action for action in menu.actions()}
            self.assertFalse(actions['Undo merge edit'].isEnabled())
            self.assertTrue(actions['Redo merge edit'].isEnabled())
            actions['Redo merge edit'].trigger()
        menu = widget.result.createStandardContextMenu()
        menu.exec = lambda point: redo(menu, point)
        with patch.object(widget.result, 'createStandardContextMenu', return_value=menu):
            widget.result.contextMenuEvent(event)
        self.assertEqual(widget.session.text, 'left')
