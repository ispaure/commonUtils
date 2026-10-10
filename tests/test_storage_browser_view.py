"""Storage uses saved index data, browser navigation and shared selection."""
import time
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from pathlib import Path
from tempfile import TemporaryDirectory
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from commonUtils.directory_index import directory_cache
from unittest.mock import patch


class StorageViewTests(QtTestCase):
    def test_navigation_stays_blank_until_current_folder_sizes_arrive(self):
        app = qt.QApplication.instance() or qt.QApplication([])
        browser = FileBrowser(calculate_folder_sizes=False)
        try:
            storage = browser.views.storage
            root = Path('/fixture'); child = root / 'child'
            result = ([], {}, {child: 0}, True)
            # Hold asynchronous work: stale results must not end the new folder's wait.
            with patch.object(storage, 'refresh'):
                storage.set_root(root)
                storage.set_root(child)
            self.assertTrue(storage.map.loading)
            self.assertTrue(storage.radial.loading)
            self.assertEqual(storage.summary.text(), '')
            storage._loaded(root, ([], {}, {root: 0}, True), '')
            self.assertTrue(storage.radial.loading)
            storage._loaded(child, result, '')
            self.assertFalse(storage.map.loading)
            self.assertFalse(storage.radial.loading)
        finally:
            browser.shutdown(); browser.close(); browser.deleteLater(); app.processEvents()

    def test_rapid_mode_switches_and_revisiting_folder_keep_charts_available(self):
        app = qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as temp:
            root = Path(temp)
            child = root / 'child'
            child.mkdir()
            (child / 'data.bin').write_bytes(b'x' * 100)
            directory_cache.get(root)
            browser = FileBrowser(root, calculate_folder_sizes=False)
            try:
                for _ in range(12):
                    for mode in (3, 4, 0, 4, 3):
                        browser.view_selector.setCurrentIndex(mode)
                        app.processEvents()
                def wait():
                    deadline = time.monotonic() + 5
                    while browser.views.storage.busy:
                        app.processEvents(); time.sleep(.005)
                        self.assertLess(time.monotonic(), deadline)
                wait()
                storage = browser.views.storage
                self.assertEqual(storage.entries, [(child, 100)])
                with patch.object(storage, '_collect', wraps=storage._collect) as collect:
                    for _ in range(20): storage.refresh()
                    wait()
                    self.assertEqual(collect.call_count, 0)
                browser.navigate(child); wait()
                browser.navigate(root); wait()
                self.assertEqual(storage.results.topLevelItemCount(), 1)
                self.assertEqual(storage.map.items, [(child, 100)])
            finally:
                browser.shutdown(); browser.close(); browser.deleteLater(); app.processEvents()

    def test_storage_bounds_materialization_of_a_large_folder(self):
        from types import SimpleNamespace
        from commonUtils._directory_metadata import Entry
        app = qt.QApplication.instance() or qt.QApplication([])
        browser = FileBrowser(calculate_folder_sizes=False)
        try:
            root = Path('/example')
            entries = [Entry(root / str(n), False, 1, 0) for n in range(4000)]
            seen = []
            def children(path, limit=None):
                seen.append(limit)
                return [(entry.path, entry.directory, entry.size) for entry in entries[:limit]]
            snapshot = SimpleNamespace(complete=True, storage_children=lambda path, limit, **kw: children(path, limit), folder_stats=lambda *a, **k: {})
            storage = browser.views.storage
            storage.operation = SimpleNamespace(isInterruptionRequested=lambda: False)
            with patch('commonUtils.ui.file_browser.storage_view.directory_cache.peek', return_value=snapshot):
                result = storage._collect(root)
            self.assertEqual(seen, [3000])
            self.assertEqual(len(result[0]), 3000)
        finally:
            browser.shutdown(); browser.close(); browser.deleteLater(); app.processEvents()

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

    def test_radial_budget_is_shared_and_deep_selection_reveals_nested_row(self):
        from types import SimpleNamespace
        from commonUtils._directory_metadata import Entry
        from commonUtils.filesystem import FolderStats
        app = qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as temp:
            root = Path(temp); big = root/'big'; small = root/'small'
            deep = small/'deep'; leaf = deep/'leaf'
            leaf.mkdir(parents=True); big.mkdir()
            file = leaf/'file.bin'; file.write_bytes(b'12345')
            children = {root: [Entry(big,True,0,0), Entry(small,True,0,0)],
                        big: [Entry(big/f'{i}.bin',False,1,0) for i in range(3100)],
                        small: [Entry(deep,True,0,0)], deep: [Entry(leaf,True,0,0)],
                        leaf: [Entry(file,False,5,0)]}
            sizes = {root: 3105, big: 3100, small: 5, deep: 5, leaf: 5}
            snapshot = SimpleNamespace(complete=True,
                storage_children=lambda path, limit, **kw: [(entry.path, entry.directory, sizes[entry.path] if entry.directory else entry.size) for entry in children.get(path, [])[:limit]],
                folder_stats=lambda paths, **kw: {path: FolderStats(size=sizes[path]) for path in paths})
            browser = FileBrowser(root,calculate_folder_sizes=False); browser.resize(1000,700); browser.show()
            try:
                with patch.object(directory_cache,'peek',return_value=snapshot):
                    browser.view_selector.setCurrentIndex(4)
                    deadline = time.monotonic()+5
                    while browser.views.storage.busy or browser.busy:
                        app.processEvents(); time.sleep(.01)
                        self.assertLess(time.monotonic(),deadline)
                    app.processEvents()
                storage = browser.views.storage
                self.assertIn(file, [path for path,size,shape in storage.radial.sectors])
                self.assertLessEqual(sum(map(len,storage.nodes.values())),3000)
                self.assertIn(small, storage.nodes)
                storage.radial.selected.emit(file); app.processEvents()
                row = storage.results.currentItem()
                self.assertEqual(row.data(0,qt.Qt.ItemDataRole.UserRole),file)
                self.assertEqual(row.parent().data(0,qt.Qt.ItemDataRole.UserRole),leaf)
                self.assertTrue(row.parent().isExpanded())
                self.assertTrue(row.parent().parent().isExpanded())
                self.assertEqual(browser.selected_objects()[0].path,file)
                self.assertFalse(storage.results.visualItemRect(row).isEmpty())
            finally:
                browser.shutdown(); browser.close(); app.processEvents()

    def test_radial_opens_hidden_unloaded_folders_and_their_descendants(self):
        app = qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as temp:
            root = Path(temp); hidden = root/'.Library'; nested = hidden/'Application Support'
            nested.mkdir(parents=True); (nested/'data.bin').write_bytes(b'abc')
            directory_cache.get(root)
            browser = FileBrowser(root,calculate_folder_sizes=False); browser.show()
            def wait():
                deadline = time.monotonic()+5
                while browser.busy or browser.views.storage.busy:
                    app.processEvents(); time.sleep(.01); self.assertLess(time.monotonic(),deadline)
                app.processEvents()
            try:
                browser.view_selector.setCurrentIndex(4); wait()
                original = browser.model.index
                # Reproduce a cached path absent from the filtered/lazy live model.
                with patch.object(browser.model, 'index', side_effect=lambda path, *args:
                                  qt.QModelIndex() if str(path) in (str(hidden),str(nested))
                                  and browser.model.rootPath() != str(path) else original(path,*args)):
                    browser.views.storage.radial.activated.emit(hidden); wait()
                    self.assertEqual(browser.navigation.directory,hidden)
                    self.assertTrue(browser.views.tree.rootIndex().isValid())
                    browser.views.storage.radial.activated.emit(nested); wait()
                    self.assertEqual(browser.navigation.directory,nested)
                    self.assertEqual(browser.views.storage.root,nested)
                    self.assertEqual(browser.view_selector.currentIndex(),4)
                browser.navigate(root); wait()
                self.assertFalse(browser.model.filter() & qt.QDir.Filter.Hidden)
            finally:
                browser.shutdown(); browser.close(); app.processEvents()

    def test_treemap_reads_one_folder_and_radial_loads_on_demand(self):
        from commonUtils._directory_store import SqlEntries
        app=qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as temp:
            root=Path(temp);child=root/'child';child.mkdir();(child/'file.txt').write_bytes(b'abc')
            directory_cache.get(root)
            browser=FileBrowser(root,calculate_folder_sizes=False)
            read=SqlEntries.storage_children;seen=[]
            def children(entries,path,limit,**kwargs):
                seen.append(path);return read(entries,path,limit,**kwargs)
            def wait():
                deadline=time.monotonic()+5
                while browser.views.storage.busy:
                    app.processEvents();time.sleep(.01);self.assertLess(time.monotonic(),deadline)
                app.processEvents()
            try:
                with patch.object(SqlEntries,'storage_children',children):
                    browser.view_selector.setCurrentIndex(3);wait()
                    self.assertEqual(seen,[root])
                    browser.views.storage.chart_selector.setCurrentIndex(1);wait()
                    self.assertIn(child,seen)
            finally:
                browser.shutdown();browser.close();app.processEvents()

    def test_middle_elision_preserves_counter_and_single_line(self):
        from commonUtils.ui.file_browser.status import IndexStatusLabel
        app=qt.QApplication.instance() or qt.QApplication([])
        label=IndexStatusLabel()
        label.resize(2 * label.fontMetrics().horizontalAdvance('last-folder · 2,500 processed this run') + 100,24)
        full='Indexing /Users/example/'+('a-very-long-folder/'*12)+'last-folder · 2,500 processed this run'
        label.setText(full);label.show();app.processEvents()
        shown=qt.QLabel.text(label)
        self.assertIn('…',shown)
        self.assertIn('last-folder',shown)
        self.assertIn('2,500 processed this run',shown)
        self.assertEqual(label.toolTip(),full)
        self.assertLessEqual(label.fontMetrics().horizontalAdvance(shown),label.width())
        self.assertFalse(label.wordWrap());label.close()

    def test_radial_center_double_click_goes_up_and_respects_browser_root(self):
        from PySide6.QtTest import QTest
        app = qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as temp:
            root = Path(temp); folder = root / 'folder'; folder.mkdir()
            (folder / 'file.txt').write_bytes(b'abc')
            directory_cache.get(root)
            browser = FileBrowser(root,calculate_folder_sizes=False)
            browser.resize(1000,700); browser.show()
            def wait():
                deadline = time.monotonic()+5
                while browser.views.storage.busy or browser.busy:
                    app.processEvents(); time.sleep(.01)
                    self.assertLess(time.monotonic(),deadline)
                app.processEvents()
            try:
                browser.view_selector.setCurrentIndex(4); wait()
                browser.navigate(folder); wait()
                radial = browser.views.storage.radial
                center = qt.QPoint(radial.width()//2,radial.height()//2)
                QTest.mouseDClick(radial,qt.Qt.MouseButton.RightButton,pos=center); wait()
                self.assertEqual(browser.navigation.directory,folder)
                QTest.mouseDClick(radial,qt.Qt.MouseButton.LeftButton,pos=center); wait()
                self.assertEqual(browser.navigation.directory,root)
                self.assertEqual(browser.view_selector.currentIndex(),4)
                QTest.mouseDClick(radial,qt.Qt.MouseButton.LeftButton,pos=center); wait()
                self.assertEqual(browser.navigation.directory,root)
            finally:
                browser.shutdown(); browser.close(); app.processEvents()
