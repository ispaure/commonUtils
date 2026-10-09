"""Displayed byte totals drive ordering, independently of formatted labels."""
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from commonUtils.filesystem import FolderStats


class SizeSortTests(unittest.TestCase):
    def test_files_folders_unknown_and_live_totals_sort_numerically(self):
        app = qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'small').write_bytes(b'x'*900)
            (root/'large').write_bytes(b'x'*2000)
            (root/'folder').mkdir(); (root/'unknown').mkdir()
            browser = FileBrowser(root, calculate_folder_sizes=False)
            try:
                parent = browser.model.index(str(root))
                deadline = time.monotonic()+5
                while browser.model.rowCount(parent) != 4:
                    app.processEvents(); time.sleep(.01)
                    self.assertLess(time.monotonic(), deadline)
                browser.model.set_folder_totals({root/'folder': FolderStats(size=1200)})
                def names(order):
                    browser.tree.sortByColumn(1, order); app.processEvents()
                    parent = browser.sort_model.mapFromSource(browser.model.index(str(root)))
                    return [browser.model.filePath(browser.sort_model.mapToSource(browser.sort_model.index(row,0,parent))).split('/')[-1] for row in range(4)]
                self.assertEqual(names(qt.Qt.SortOrder.AscendingOrder), ['small','folder','large','unknown'])
                self.assertEqual(names(qt.Qt.SortOrder.DescendingOrder), ['large','folder','small','unknown'])
                browser.model.set_folder_totals({root/'folder': FolderStats(size=3000)})
                self.assertEqual(names(qt.Qt.SortOrder.DescendingOrder), ['folder','large','small','unknown'])
            finally:
                browser.shutdown(); browser.close(); app.processEvents()
