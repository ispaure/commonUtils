"""Outline presentation never interprets navigation targets as filesystem paths."""
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.outline import OutlineEntry, OutlineList, OutlineTree


class OutlineTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_list_and_tree_keep_opaque_targets_and_duplicate_labels(self):
        targets = [object(), object()]
        entries = [OutlineEntry('first', 'Same', targets[0]),
                   OutlineEntry('second', 'Same', targets[1], 2)]
        flat, tree = OutlineList(), OutlineTree()
        flat.set_entries(entries)
        tree.set_entries(entries)
        self.assertEqual(flat.count(), 2)
        self.assertEqual(tree.topLevelItemCount(), 1)
        self.assertEqual(tree.topLevelItem(0).childCount(), 1)
        self.assertIs(flat.item(1).data(qt.Qt.ItemDataRole.UserRole), targets[1])
        self.assertIs(tree.items_by_id['second'].data(0, qt.Qt.ItemDataRole.UserRole), targets[1])
        flat.set_entries([])
        tree.set_entries([])
        self.assertEqual(flat.count(), 0)
        self.assertEqual(tree.items_by_id, {})
