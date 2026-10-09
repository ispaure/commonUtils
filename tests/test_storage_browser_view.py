"""Storage uses saved index data, browser navigation and shared selection."""
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from commonUtils.directory_index import directory_cache
from unittest.mock import patch


class StorageViewTests(unittest.TestCase):
    def test_cached_charts_selection_drilldown_and_mode_switch(self):
        app=qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'folder';folder.mkdir();file=folder/'large.bin';file.write_bytes(b'x'*1200)
            small=root/'small.bin';small.write_bytes(b'x'*300)
            directory_cache.get(root)
            browser=FileBrowser(root,calculate_folder_sizes=False)
            browser.resize(1000,700);browser.show()
            def wait():
                deadline=time.monotonic()+5
                while browser.views.storage.busy or browser.busy:
                    app.processEvents();time.sleep(.01)
                    self.assertLess(time.monotonic(),deadline)
                app.processEvents()
            try:
                with patch.object(directory_cache,'get',side_effect=AssertionError('Storage initiated another scan')):
                    browser.view_selector.setCurrentIndex(3);wait()
                    storage=browser.views.storage
                    self.assertEqual(storage.chart_selector.currentText(),'Treemap')
                    self.assertEqual(storage.entries,[(folder,1200),(small,300)])
                    self.assertTrue(browser.preview_panel.isHidden())
                    self.assertTrue(browser.preview_toggle.isHidden())
                    self.assertTrue(storage.chart_selector.isHidden())
                    self.assertEqual(storage.splitter.orientation(), qt.Qt.Orientation.Horizontal)
                    self.assertGreater(storage.results.x(), storage.charts.x())
                    storage.map.selected.emit(folder);wait()
                    self.assertEqual(browser.selected_objects()[0].path,folder)
                    browser.view_selector.buttons[4].click();wait()
                    self.assertEqual(storage.charts.currentIndex(),1)
                    self.assertEqual(browser.view_selector.currentIndex(),4)
                    self.assertEqual(storage.results.topLevelItem(0).data(0,qt.Qt.ItemDataRole.UserRole),folder)
                    self.assertTrue(storage.radial.sectors)
                    self.assertIn(file,[path for path,size,shape in storage.radial.sectors])
                    storage.radial.activated.emit(folder);wait()
                    self.assertEqual(browser.navigation.directory,folder)
                    self.assertEqual(storage.entries,[(file,1200)])
                    browser.navigation.back.click();wait()
                    self.assertEqual(browser.navigation.directory,root)
                    browser.view_selector.setCurrentIndex(0);app.processEvents()
                    self.assertEqual(browser.views.currentIndex(),0)
            finally:
                browser.shutdown();browser.close();app.processEvents()

    def test_treemap_reads_one_folder_and_radial_loads_on_demand(self):
        from commonUtils._directory_store import SqlEntries
        app=qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as temp:
            root=Path(temp);child=root/'child';child.mkdir();(child/'file.txt').write_bytes(b'abc')
            directory_cache.get(root)
            browser=FileBrowser(root,calculate_folder_sizes=False)
            read=SqlEntries.children;seen=[]
            def children(entries,path,limit=None):
                seen.append(path);return read(entries,path,limit)
            def wait():
                deadline=time.monotonic()+5
                while browser.views.storage.busy:
                    app.processEvents();time.sleep(.01);self.assertLess(time.monotonic(),deadline)
                app.processEvents()
            try:
                with patch.object(SqlEntries,'children',children):
                    browser.view_selector.setCurrentIndex(3);wait()
                    self.assertEqual(seen,[root])
                    browser.views.storage.chart_selector.setCurrentIndex(1);wait()
                    self.assertIn(child,seen)
            finally:
                browser.shutdown();browser.close();app.processEvents()

    def test_middle_elision_preserves_counter_and_single_line(self):
        from commonUtils.ui.file_browser.status import IndexStatusLabel
        app=qt.QApplication.instance() or qt.QApplication([])
        label=IndexStatusLabel();label.resize(720,24)
        full='Indexing /Users/example/'+('a-very-long-folder/'*12)+'last-folder · 2,500 processed this run'
        label.setText(full);label.show();app.processEvents()
        shown=qt.QLabel.text(label)
        self.assertIn('…',shown)
        self.assertIn('last-folder',shown)
        self.assertIn('2,500 processed this run',shown)
        self.assertEqual(label.toolTip(),full)
        self.assertLessEqual(label.fontMetrics().horizontalAdvance(shown),label.width())
        self.assertFalse(label.wordWrap());label.close()
