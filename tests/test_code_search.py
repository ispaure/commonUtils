import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
from commonUtils.ui.code_editor.search import SearchPanel,find_matches


class CodeSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=qt.QApplication.instance() or qt.QApplication([])
    def test_unicode_case_words_regex_and_selection(self):
        matches,_=find_matches('😀 cat CAT scatter','cat',whole=True)
        self.assertEqual([(m.start,m.length) for m in matches],[(3,3),(7,3)])
        self.assertEqual(len(find_matches('cat CAT','cat',case=True)[0]),1)
        matches,_=find_matches('x=12 y=34',r'(\w)=(\d+)','$2:$1',regex=True,scope=(5,9))
        self.assertEqual(matches[0].replacement,'34:y')
        with self.assertRaises(ValueError):find_matches('text','[',regex=True)
        with self.assertRaises(ValueError):find_matches('a','(a)','$2',regex=True)
        self.assertTrue(find_matches('a'*50001,'a')[1])
    def test_replace_all_is_single_undo_and_wrap_off_stops(self):
        editor=CodeEdit();editor.setPlainText('😀 cat CAT');panel=SearchPanel();panel.editor=editor
        panel.matches= find_matches(editor.toPlainText(),'cat','dog')[0]
        panel.replace_all();self.assertEqual(editor.toPlainText(),'😀 dog dog');editor.undo();self.assertEqual(editor.toPlainText(),'😀 cat CAT')
        panel.matches=find_matches(editor.toPlainText(),'cat')[0];panel.wrap.setChecked(False)
        editor.moveCursor(qt.QTextCursor.MoveOperation.End);panel.show();panel.find();self.assertIn('wrap is off',panel.summary.text())
        panel.close_panel();panel.editor=None;panel.deleteLater();editor.deleteLater()

    def test_async_query_change_and_selection_scope(self):
        from time import monotonic,sleep
        editor=CodeEdit();editor.setPlainText('one two one');panel=SearchPanel();panel.set_editor(editor);panel.show()
        cursor=editor.textCursor();cursor.setPosition(4);cursor.setPosition(7,qt.QTextCursor.MoveMode.KeepAnchor);editor.setTextCursor(cursor)
        panel.selection.setChecked(True);panel.query.setText('two');panel.replacement.setText('changed');panel._search()
        deadline=monotonic()+5
        while panel.busy:
            self.assertLess(monotonic(),deadline);self.app.processEvents();sleep(.005)
        self.assertEqual(len(panel.matches),1);panel.replace_all();self.assertEqual(editor.toPlainText(),'one changed one');editor.undo()
        editor.setReadOnly(True);panel.matches=find_matches(editor.toPlainText(),'one','bad')[0];panel.replace_all();self.assertEqual(editor.toPlainText(),'one two one')
        panel.close_panel();panel.set_editor(None);panel.deleteLater();editor.deleteLater()
