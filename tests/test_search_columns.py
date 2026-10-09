"""Search layouts prioritize names, including narrow tabs and long extensions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.search_columns import configure_search_columns, describe_search_row


class SearchColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def tree(self):
        tree = qt.QTreeWidget()
        tree.setHeaderLabels(['Name', 'Type', 'Size', 'Path'])
        tree.setRootIsDecorated(False)
        configure_search_columns(tree)
        row = qt.QTreeWidgetItem(['A longer useful filename.epub', 'epub', '12.8 MB',
                                 '/a/very/long/path/to/A longer useful filename.epub'])
        describe_search_row(row, tree)
        tree.addTopLevelItem(row)
        self.addCleanup(tree.deleteLater)
        return tree

    def test_names_wider_than_paths_at_compact_and_wide_sizes(self):
        tree = self.tree()
        for width in (600, 1200):
            tree.resize(width, 400); tree.show(); self.app.processEvents()
            self.assertGreater(tree.columnWidth(0), tree.columnWidth(3))
            self.assertLess(tree.columnWidth(1), 90)
            self.assertLess(tree.columnWidth(2), 110)
        self.assertEqual(tree.topLevelItem(0).toolTip(3), tree.topLevelItem(0).text(3))
        self.assertGreater(tree.topLevelItem(0).font(0).weight(), tree.topLevelItem(0).font(3).weight())

    def test_manual_path_width_is_kept_on_window_resize(self):
        tree = self.tree(); tree.resize(900, 400); tree.show(); self.app.processEvents()
        tree.setColumnWidth(3, 150)
        tree.resize(1200, 400); self.app.processEvents()
        self.assertEqual(tree.columnWidth(3), 150)

    def test_unusually_long_type_cannot_take_over_name_column(self):
        tree = self.tree()
        tree.topLevelItem(0).setText(1, 'long-extension-' * 30)
        tree.resize(600, 400); tree.show(); self.app.processEvents()
        self.assertLessEqual(tree.columnWidth(1), 130)
        self.assertGreater(tree.columnWidth(0), tree.columnWidth(1))
