import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor.views import EditorViews
from commonUtils.ui.code_editor.folding import fold_ranges


class FoldingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_ranges_ignore_strings_comments_and_support_nested_blocks(self):
        self.assertEqual(fold_ranges('def a():\n    if x:\n        pass\nend', 'python'), {1: 2, 0: 2})
        ranges = fold_ranges('{\n "brace": "}",\n "nested": [\n  1\n ]\n}', 'json')
        self.assertEqual(ranges, {2: 4, 0: 5})
        self.assertEqual(fold_ranges('<r>\n<!-- <bad> -->\n<a>\nx\n</a>\n</r>', 'xml'), {2: 4, 0: 5})
        self.assertEqual(fold_ranges('x' * (256 * 1024 + 1), 'python'), {})

    def test_folds_share_views_reveal_search_and_expand_after_edit(self):
        views = EditorViews()
        try:
            primary = views.primary
            primary.setPlainText('{\n "a": [\n  1\n ]\n}')
            primary.folding.configure('json')
            views.set_split(qt.Qt.Orientation.Horizontal)
            primary.fold_all()
            self.assertFalse(primary.document().findBlockByNumber(2).isVisible())
            self.assertIs(primary.folding, views.secondary.folding)
            cursor = qt.QTextCursor(primary.document().findBlockByNumber(2))
            views.secondary.setTextCursor(cursor)
            self.assertTrue(primary.document().findBlockByNumber(2).isVisible())
            primary.fold_all()
            primary.insertPlainText(' ')
            self.app.processEvents()
            self.assertTrue(all(primary.document().findBlockByNumber(i).isVisible() for i in range(primary.blockCount())))
            primary.undo()
            self.assertEqual(primary.toPlainText(), '{\n "a": [\n  1\n ]\n}')
        finally:
            views.deleteLater()
