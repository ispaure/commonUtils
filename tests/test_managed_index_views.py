"""Storage and inline search consume automatic browser indexing without rescanning."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic,sleep
import unittest
from unittest.mock import patch
from commonUtils.directory_index import DirectoryCache
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from commonUtils.ui.file_browser.storage import StorageDialog


class ManagedViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp=TemporaryDirectory();self.base=Path(self.temp.name)
        self.root=self.base/'files';self.root.mkdir();(self.root/'item.txt').write_bytes(b'abc')
        self.cache=DirectoryCache(database=self.base/'cache'/'index.sqlite3')
        self.patches=[patch(name,self.cache) for name in ('commonUtils.directory_index.directory_cache',
            'commonUtils.ui.file_browser.index_worker.directory_cache','commonUtils.ui.file_browser.index_search.directory_cache',
            'commonUtils.ui.file_browser.discovery.directory_cache')]
        for item in self.patches:item.start()
        self.browser=FileBrowser(self.root);self.browser.show();self.dialogs=[]
        self.wait(lambda:not self.browser.folder_busy)

    def tearDown(self):
        for dialog in self.dialogs:dialog.close()
        self.browser.close()
        self.wait(lambda:not self.browser.folder_busy and not self.browser.index_search.busy and all(not d.busy for d in self.dialogs))
        self.app.sendPostedEvents(None,qt.QEvent.Type.DeferredDelete)
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def wait(self,condition):
        deadline=monotonic()+8
        while not condition():
            self.assertLess(monotonic(),deadline);self.app.processEvents();sleep(.005)
        self.app.processEvents()

    def open(self,kind):
        dialog=kind(self.browser);self.dialogs.append(dialog);dialog.show();return dialog

    def test_storage_opens_with_cached_map_and_search_reads_cache_while_paused(self):
        self.browser.set_folder_sizes_enabled(False)
        with patch.object(self.cache,'get',side_effect=AssertionError('Viewer started a scan')):
            storage=self.open(StorageDialog)
            self.wait(lambda:storage.snapshot is not None and not storage.busy)
            self.assertEqual(storage.totals[self.root],3)
            self.assertTrue(storage.map.items)
            self.assertTrue(storage.rebuild_button.isHidden());self.assertTrue(storage.clear_button.isHidden())
            self.assertEqual(storage.refresh_button.text(),'Refresh view')
            self.assertTrue(storage.task.isHidden())
            search=self.browser.open_search();self.browser.search_bar.setText('item')
            self.wait(lambda:not search.busy and not search.debounce.isActive())
            self.assertEqual(search.results.topLevelItemCount(),1)
            storage.refresh_button.click();self.wait(lambda:not storage.busy)
            self.assertEqual(storage.totals[self.root],3)
            self.assertTrue(self.browser.model.folder_totals)

    def test_open_views_follow_browser_index_updates(self):
        storage=self.open(StorageDialog);search=self.browser.open_search()
        self.browser.search_bar.setText('new')
        self.wait(lambda:storage.snapshot is not None and not storage.busy and not search.busy and not search.debounce.isActive())
        (self.root/'new.txt').write_bytes(b'12345');self.browser.refresh()
        self.wait(lambda:not self.browser.folder_busy and not storage.busy and not search.busy and
                  storage.totals.get(self.root)==8 and search.results.topLevelItemCount()==1)
        self.assertIn('up to date',storage.index_status.text())
