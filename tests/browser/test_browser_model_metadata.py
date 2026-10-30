"""Repeated GUI roles reuse watched metadata without restatting every row."""
from pathlib import Path
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.runtime.browsing import BrowseRole
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.model import BrowserFileSystemModel, ByteSortModel

TEST_STAGE = TestStage.REGRESSION


class ModelMetadataTests(QtTestCase):
    def test_sort_reuses_row_values_across_insertions_but_observes_changes(self):
        class Source(qt.QStandardItemModel):
            reads = 0
            def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
                self.reads += 1
                return super().data(index, role)
        source = Source()
        for label in ('entry-2', 'entry-10'):
            item = qt.QStandardItem(label)
            item.setData(False, BrowseRole.Container)
            source.appendRow(item)
        proxy = ByteSortModel(source)
        self.assertTrue(proxy.lessThan(source.index(0, 0), source.index(1, 0)))
        reads = source.reads
        for _ in range(100):
            self.assertTrue(proxy.lessThan(source.index(0, 0), source.index(1, 0)))
        self.assertEqual(source.reads, reads)
        source.insertRow(0, qt.QStandardItem('new'))
        self.assertTrue(proxy.lessThan(source.index(1, 0), source.index(2, 0)))
        self.assertEqual(source.reads, reads)
        source.setData(source.index(2, 0), 'entry-1', qt.Qt.ItemDataRole.DisplayRole)
        self.assertFalse(proxy.lessThan(source.index(1, 0), source.index(2, 0)))
        source.setData(source.index(1, 0), True, BrowseRole.Container)
        self.assertTrue(proxy.lessThan(source.index(1, 0), source.index(2, 0)))

    def test_paint_and_sort_share_one_turn_then_read_changed_metadata(self):
        directory = self.temporary_directory()
        root = Path(directory.name)
        path = root / 'entry.bin'
        path.write_bytes(b'abc')
        owner = qt.QWidget()
        model = BrowserFileSystemModel(owner)
        parent = model.setRootPath(str(root))
        self.wait_until(lambda: model.rowCount(parent) == 1)
        index = model.index(str(path))
        model.item(index)  # Resolve lazily registered built-in file types first.
        original = model.item(index)
        with patch.object(Path, 'stat', side_effect=AssertionError('GUI role restatted file')):
            for _ in range(100):
                self.assertIs(model.item(index), original)
                self.assertEqual(model.data(index, qt.Qt.ItemDataRole.DisplayRole), 'entry.bin')
                self.assertEqual(model.data(index, BrowseRole.SortValue), 'entry.bin')
                self.assertEqual(model.data(index.siblingAtColumn(1), BrowseRole.SortValue), 3)
        path.write_bytes(b'longer content')
        qt.QApplication.processEvents()
        self.assertIsNot(model.item(index), original)
        self.assertEqual(model.item(index).size, 14)
        # Explicit path lookups retain their immediate, nanosecond stat contract.
        self.assertEqual(model.object_for_path(path).size, 14)
        owner.close()
