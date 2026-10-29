
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
from commonUtils.ui.code_editor.markers import line_changes


class MarkerTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_add_modify_delete_and_eof(self):
        for before, after, kind, start, end in [
            ('a\n', 'a\nb\n', 'add', 1, 2),
            ('a\n', 'b\n', 'modify', 0, 1),
            ('a\nb\n', 'a\n', 'delete', 1, 1),
            ('a', '', 'delete', 0, 0),
            ('a\n', 'a', 'modify', 0, 1),
        ]:
            change, = line_changes(before, after)
            self.assertEqual((change.kind, change.start, change.end), (kind, start, end))

    def test_unequal_replacements_keep_removed_and_added_lines_distinct(self):
        changes = line_changes('keep\nold\nremoved\nend\n', 'keep\nnew\nend\n')
        self.assertEqual([c.kind for c in changes], ['modify', 'delete'])
        self.assertEqual((changes[1].old_start, changes[1].old_end, changes[1].start, changes[1].end),
                         (2, 3, 2, 2))
        changes = line_changes('keep\nold\nend\n', 'keep\nnew\nadded\nend\n')
        self.assertEqual([c.kind for c in changes], ['modify', 'add'])
        self.assertEqual((changes[1].old_start, changes[1].old_end, changes[1].start, changes[1].end),
                         (2, 2, 2, 3))

    def test_red_deletion_and_blue_modification_both_render_at_eof(self):
        editor = CodeEdit()
        self.addCleanup(editor.deleteLater)
        editor.setPlainText('new')
        editor.set_line_changes(line_changes('old\nremoved', 'new'))
        editor.resize(480, 240)
        editor.show()
        self.app.processEvents()
        block = editor.document().firstBlock()
        top = round(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
        height = round(editor.blockBoundingRect(block).height())
        image = editor.gutter.grab().toImage()
        self.assertEqual(image.pixelColor(3, top + 4).name(), '#408bd6')
        self.assertEqual(image.pixelColor(3, top + height - 2).name(), '#d55e00')

    def test_added_block_has_a_clean_continuous_bar(self):
        editor = CodeEdit()
        editor.resize(480, 240)
        editor.setPlainText('first\nsecond\nthird\n')
        editor.set_line_changes(line_changes('', editor.toPlainText()))
        editor.show()
        self.app.processEvents()
        image = editor.gutter.grab().toImage()
        for row in range(3):
            block = editor.document().findBlockByNumber(row)
            top = round(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
            height = round(editor.blockBoundingRect(block).height())
            self.assertEqual(image.pixelColor(3, top + height // 2).name(), '#009e73')
            self.assertNotEqual(image.pixelColor(0, top + height // 2).name(), '#009e73')

    def test_render_markers_separate_from_folding_and_numbers(self):
        editor = CodeEdit()
        self.addCleanup(editor.deleteLater)
        editor.resize(480, 240)
        before = 'def example():\n    old = 1\n    return old\n# deleted\n'
        after = 'def example():\n    new = 2\n    return old\n'
        editor.setPlainText(after)
        editor.folding.configure('python')
        editor.set_line_changes(line_changes(before, after), 'Git index')
        editor.show()
        self.app.processEvents()
        image = editor.gutter.grab().toImage()
        self.assertEqual(image.pixelColor(3, editor.fontMetrics().height() + 6).name(), '#408bd6')
        self.assertEqual(editor.gutter.toolTip(), 'Git index')
        editor.gutter_click(qt.QPoint(3, 8))
        self.assertFalse(editor.folding.collapsed)
