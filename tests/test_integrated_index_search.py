"""Automatic indexing, recursive cached queries, watcher updates and normal actions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest
from unittest.mock import patch
from commonUtils.directory_index import DirectoryCache
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser


class IntegratedSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp=TemporaryDirectory();self.base=Path(self.temp.name)
        self.root=self.base/'Documents';self.root.mkdir();(self.root/'nested').mkdir()
        self.file=self.root/'nested'/'Needle.TXT';self.file.write_text('abc')
        self.cache=DirectoryCache(database=self.base/'cache'/'index.sqlite3')
        self.patches=[patch(name,self.cache) for name in ('commonUtils.directory_index.directory_cache',
             'commonUtils.ui.file_browser.index_worker.directory_cache','commonUtils.ui.file_browser.index_search.directory_cache',
             'commonUtils.ui.file_browser.discovery.directory_cache')]
        for p in self.patches:p.start()
        self.browser=FileBrowser(self.root);self.browser.show();self.browsers=[self.browser]
        self.wait(lambda:not self.browser.folder_busy)

    def tearDown(self):
        for browser in self.browsers: browser.close()
        self.wait(lambda:all(not (b.busy or b.folder_busy or b.index_search.busy or b.views.cover_busy) for b in self.browsers))
        self.app.sendPostedEvents(None,qt.QEvent.Type.DeferredDelete)
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def wait(self, condition):
        deadline=monotonic()+8
        while not condition():
            self.assertLess(monotonic(),deadline)
            self.app.processEvents();sleep(.01)
        self.app.processEvents()

    def search(self, text, expected):
        self.browser.search_bar.setText(text)
        self.wait(lambda:self.browser.index_search.total==expected and not self.browser.index_search.busy
                  and not self.browser.index_search.debounce.isActive())

    def test_recursive_search_queries_sql_without_new_walk_and_preserves_selection_and_clear(self):
        with patch('commonUtils.directory_index.os.scandir',side_effect=AssertionError('Search traversed filesystem')):
            self.search('nEEdLE',1)
            row=self.browser.index_search.results.topLevelItem(0)
            self.assertEqual(row.data(0,qt.Qt.ItemDataRole.UserRole),self.file)
            row.setSelected(True);self.app.processEvents()
            self.assertEqual(self.browser.selected_objects()[0].path,self.file)
            self.browser.search_bar.clear();self.app.processEvents()
            self.assertIs(self.browser.list_stack.currentWidget(),self.browser.views)

    def test_show_result_in_browser_uses_normal_parent_navigation(self):
        self.search('needle',1)
        self.assertTrue(self.browser.index_search.show_in_browser(self.file))
        self.wait(lambda:not self.browser.folder_busy)
        self.assertEqual(self.browser.navigation.directory,self.file.parent)
        self.assertEqual(self.browser.selected_objects()[0].path,self.file)
        self.assertFalse(self.browser.search_bar.text())

    def test_real_watchers_update_additions_removal_rename_and_visible_file_metadata(self):
        self.search('needle',1)
        new=self.root/'Needle-new.txt';new.write_text('new')
        self.wait(lambda:self.browser.index_search.total==2 and not self.browser.folder_busy)
        new.write_text('longer content')
        self.wait(lambda:(self.cache.peek(self.root).entry(new).size==14 and not self.browser.folder_busy))
        renamed=self.root/'Other.txt';new.rename(renamed)
        self.wait(lambda:self.browser.index_search.total==1 and not self.browser.folder_busy)
        renamed.unlink()
        self.wait(lambda:self.cache.peek(self.root).entry(renamed) is None and not self.browser.folder_busy)

    def test_paged_results_sort_globally_and_new_instance_uses_saved_index(self):
        for number in range(505):(self.root/f'match-{number}.bin').write_bytes(b'x'*number)
        self.browser.refresh();self.wait(lambda:not self.browser.folder_busy)
        self.search('match-',505)
        self.assertEqual(self.browser.index_search.results.topLevelItemCount(),500)
        self.browser.index_search._sort_changed(2)
        self.wait(lambda:not self.browser.index_search.busy)
        self.browser.index_search._page(1);self.wait(lambda:not self.browser.index_search.busy)
        self.assertEqual(self.browser.index_search.results.topLevelItemCount(),5)
        row=self.browser.index_search.results.topLevelItem(0)
        self.assertEqual(row.data(0,qt.Qt.ItemDataRole.UserRole).name,'match-500.bin')
        restarted=DirectoryCache(database=self.cache.database)
        with patch('commonUtils.directory_index.os.scandir',side_effect=AssertionError('Restarted query scanned')):
            self.assertEqual(restarted.peek(self.root).search_page('match-')[1],505)

    def test_cached_subtree_is_scoped_and_reused_without_duplicate_enumeration(self):
        (self.root/'Needle-outside.txt').write_text('outside');self.browser.refresh()
        self.wait(lambda:not self.browser.folder_busy)
        with patch('commonUtils.directory_index.os.scandir',side_effect=AssertionError('Subtree enumerated again')):
            sub=self.cache.peek(self.file.parent)
            self.assertEqual(sub.search_page('needle')[1],1)
            self.assertEqual(set(sub.folder_stats()),{self.file.parent})
            fresh=self.cache.get(self.file.parent)
            self.assertEqual(fresh.search_page('needle')[1], 1)
            self.assertEqual(fresh.folder_stats()[self.file.parent].size,3)

    def test_partial_discovery_updates_search_before_scan_finishes_and_close_cancels(self):
        import os
        real = os.scandir
        for number in range(1100): (self.root / f'progress-{number}.bin').write_bytes(b'x')
        class SlowDirectory:
            def __init__(self, path): self.entries=real(path)
            def __enter__(self): return self
            def __exit__(self, *args): self.entries.close()
            def __iter__(self):
                for entry in self.entries:
                    sleep(.002)
                    yield entry
        def scandir(path): return SlowDirectory(path) if Path(path)==self.root else real(path)
        with patch('commonUtils.directory_index.os.scandir', side_effect=scandir):
            self.browser.refresh()
            self.browser.search_bar.setText('progress-')
            self.wait(lambda: 0 < self.browser.index_search.total < 1100)
            self.assertTrue(self.browser.folder_busy)
            self.assertIn('incomplete', self.browser.index_search.summary.text())
            self.browser.close()
            self.wait(lambda: not self.browser.folder_busy and not self.browser.index_search.busy)
        self.assertIsNotNone(self.cache.status(self.root))
        self.assertGreater(self.cache.status(self.root)['entries'], 0)

    def test_rapid_queries_and_navigation_discard_obsolete_results(self):
        self.browser.search_bar.setText('needle');self.browser.index_search.refresh()
        self.browser.search_bar.setText('absent')
        self.wait(lambda:not self.browser.index_search.busy and not self.browser.index_search.debounce.isActive())
        self.assertEqual(self.browser.index_search.results.topLevelItemCount(),0)
        self.browser.navigate(self.file.parent)
        self.wait(lambda:not self.browser.folder_busy)
        self.assertFalse(self.browser.search_bar.text())
