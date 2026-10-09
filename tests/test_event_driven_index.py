"""Completed browsers stay idle; visits check one folder and Refresh checks deeper."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest
from unittest.mock import patch
from commonUtils.directory_index import DirectoryCache
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser


class EventDrivenIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory(); self.base = Path(self.temp.name)
        self.root = self.base / 'files'; self.root.mkdir()
        self.child = self.root / 'child'; self.child.mkdir()
        self.deep = self.child / 'deep'; self.deep.mkdir()
        (self.deep / 'original.txt').write_bytes(b'abc')
        self.cache = DirectoryCache(database=self.base / 'cache' / 'index.sqlite3')
        self.patches = [patch(name, self.cache) for name in (
            'commonUtils.directory_index.directory_cache',
            'commonUtils.ui.file_browser.index_worker.directory_cache',
            'commonUtils.ui.file_browser.index_search.directory_cache')]
        for item in self.patches: item.start()
        self.browser = FileBrowser(self.root); self.browser.show()
        self.wait(lambda: not self.browser.folder_busy)

    def tearDown(self):
        self.browser.close()
        self.wait(lambda: not self.browser.folder_busy)
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def wait(self, condition):
        deadline = monotonic() + 8
        while not condition():
            self.assertLess(monotonic(), deadline)
            self.app.processEvents(); sleep(.005)
        self.app.processEvents()

    def unwatch(self):
        watcher = self.browser.index_watcher
        paths = watcher.directories() + watcher.files()
        if paths: watcher.removePaths(paths)

    def test_completed_scan_has_no_polling_or_pause_control(self):
        self.assertFalse(self.browser.reconcile_timer.isActive())
        self.assertTrue(self.browser.index_pause_button.isHidden())
        self.assertIn('checked', self.browser.index_status.text().lower())

    def test_visiting_folder_and_reopening_same_folder_find_new_files(self):
        self.unwatch()
        added = self.child / 'added.txt'; added.write_bytes(b'12345')
        with patch.object(self.cache, '_validate', side_effect=AssertionError('Whole-tree validation')):
            self.browser.navigate(self.child)
            self.wait(lambda: not self.browser.folder_busy)
            self.assertEqual(self.browser.model.folder_totals[self.child].size, 8)
            self.unwatch()
            second = self.child / 'second.txt'; second.write_bytes(b'xx')
            self.browser.navigate(self.child)
            self.wait(lambda: not self.browser.folder_busy)
            self.assertEqual(self.browser.model.folder_totals[self.child].size, 10)
        self.assertIsNotNone(self.cache.peek(self.root).entry(second))
        self.assertFalse(self.browser.reconcile_timer.isActive())

    def test_notification_updates_changed_file_without_deep_validation(self):
        self.unwatch()
        item = self.deep / 'original.txt'; item.write_bytes(b'longer data')
        with patch.object(self.cache, '_validate', side_effect=AssertionError('Whole-tree validation')):
            self.browser._indexed_path_changed(str(item))
            self.wait(lambda: not self.browser.folder_busy and
                      self.browser.model.folder_totals[self.root].size == 11)

    def test_explicit_refresh_finds_changes_in_unwatched_descendants(self):
        self.unwatch()
        added = self.deep / 'added.txt'; added.write_bytes(b'12345')
        self.browser.refresh()
        self.wait(lambda: not self.browser.folder_busy)
        self.assertEqual(self.browser.model.folder_totals[self.root].size, 8)
        self.assertIsNotNone(self.cache.peek(self.root).entry(added))

    def test_pause_keeps_cached_sizes_during_navigation_and_resume_checks_changes(self):
        self.browser._toggle_index_pause()
        self.assertEqual(self.browser.index_pause_button.text(), 'Resume')
        self.unwatch()
        added = self.child / 'added.txt'; added.write_bytes(b'12345')
        with patch.object(self.cache, 'reconcile_folder', side_effect=AssertionError('Paused scan')):
            self.browser.navigate(self.child)
            self.wait(lambda: not self.browser.folder_busy)
        self.assertEqual(self.browser.model.folder_totals[self.child].size, 3)
        self.assertIn('paused', self.browser.index_status.text())
        self.browser._toggle_index_pause()
        self.wait(lambda: not self.browser.folder_busy)
        self.assertEqual(self.browser.model.folder_totals[self.child].size, 8)
