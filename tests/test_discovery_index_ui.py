"""Search communicates saved checkpoints and supports resuming/rebuilding/clearing."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from threading import Event
from time import monotonic, sleep
import unittest
from unittest.mock import patch

from commonUtils.directory_index import DirectoryCache
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.discovery import SearchDialog
from commonUtils.ui.file_browser.storage import StorageDialog


class DiscoveryIndexUiTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name).resolve()
        self.root = folder / 'files'; self.root.mkdir()
        (self.root / 'nested').mkdir()
        (self.root / 'nested' / 'file.txt').write_text('contents')
        self.cache = DirectoryCache(database=folder / 'support' / 'index.sqlite3')
        self.patch = patch('commonUtils.ui.file_browser.discovery.directory_cache', self.cache)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.browser = qt.QWidget()
        self.browser.navigation = SimpleNamespace(directory=self.root)
        self.addCleanup(self.browser.deleteLater)

    def dialog(self, kind=SearchDialog):
        dialog = kind(self.browser)
        dialog.show()
        def close():
            dialog.task.request_cancel()
            self.wait(dialog)
            dialog.close()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.addCleanup(close)
        return dialog

    def wait(self, dialog):
        deadline = monotonic() + 5
        while dialog.busy:
            self.assertLess(monotonic(), deadline)
            self.app.processEvents(); sleep(.005)
        self.app.processEvents()

    def test_search_saved_results_rebuild_and_clear(self):
        dialog = self.dialog()
        dialog.query.setText('FILE')
        dialog.search_button.click(); self.wait(dialog)
        self.assertEqual(dialog.results.topLevelItemCount(), 1)
        self.assertIn('saved on disk', dialog.freshness.text())
        dialog.search_button.click(); self.wait(dialog)
        self.assertTrue(dialog.snapshot.reused)
        dialog.rescan_button.click(); self.wait(dialog)
        self.assertFalse(dialog.snapshot.reused)
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
            dialog.clear_button.click(); self.wait(dialog)
        self.assertIsNone(dialog.snapshot)
        self.assertEqual(dialog.results.topLevelItemCount(), 0)
        self.assertIn('cleared', dialog.summary.text())
        self.assertTrue(dialog.clear_button.isEnabled())

    def test_cancel_reports_saved_partial_and_search_resumes_it(self):
        dialog = self.dialog()
        entered, release = Event(), Event()
        original = self.cache._scan_folder
        def checkpoint(db, generation, root, recursive, folder, cancelled, report):
            original(db, generation, root, recursive, folder, cancelled, report)
            if folder == self.root:
                entered.set(); release.wait(3)
        with patch.object(self.cache, '_scan_folder', checkpoint):
            dialog.query.setText('file')
            dialog.search_button.click()
            try:
                self.assertTrue(entered.wait(2))
                dialog.task.request_cancel()
            finally:
                release.set(); self.wait(dialog)
        self.assertIn('Scan paused', dialog.summary.text())
        self.assertIn('Run again to resume', dialog.summary.text())
        self.assertIn('Partial index saved', dialog.freshness.text())
        self.assertEqual(dialog.task.message.text(), 'Cancelled.')
        self.assertTrue(dialog.search_button.isEnabled())
        dialog.search_button.click(); self.wait(dialog)
        self.assertTrue(dialog.snapshot.resumed)
        self.assertEqual(dialog.results.topLevelItemCount(), 1)

    def test_storage_uses_same_index_and_offers_resume_and_rebuild(self):
        first = self.cache.get(self.root)
        dialog = self.dialog(StorageDialog)
        dialog.refresh_button.click(); self.wait(dialog)
        self.assertTrue(dialog.snapshot.reused)
        self.assertEqual(dialog.snapshot.scanned_at, first.scanned_at)
        self.assertEqual(dialog.totals[self.root], 8)
        self.assertIn('Resume', dialog.refresh_button.text())
        dialog.rebuild_button.click(); self.wait(dialog)
        self.assertFalse(dialog.snapshot.reused)

    def test_search_pages_include_all_matches_without_overloading_the_tree(self):
        for index in range(505):
            (self.root / f'match{index}.txt').write_text('test')
        dialog = self.dialog()
        dialog.query.setText('match')
        dialog.search_button.click(); self.wait(dialog)
        self.assertEqual(dialog.results.topLevelItemCount(), 500)
        self.assertIn('of 505 matches', dialog.summary.text())
        self.assertFalse(dialog.previous_button.isEnabled())
        self.assertTrue(dialog.next_button.isEnabled())
        dialog.next_button.click(); self.wait(dialog)
        self.assertEqual(dialog.results.topLevelItemCount(), 5)
        self.assertIn('501–505', dialog.summary.text())
        self.assertTrue(dialog.previous_button.isEnabled())
        self.assertFalse(dialog.next_button.isEnabled())
        dialog.previous_button.click(); self.wait(dialog)
        self.assertEqual(dialog.results.topLevelItemCount(), 500)
        (self.root / 'match504.txt').write_text('x' * 1000)
        dialog.rescan_button.click(); self.wait(dialog)
        dialog.results.header().setSortIndicator(2, qt.Qt.SortOrder.DescendingOrder)
        self.wait(dialog)
        self.assertEqual(dialog.results.topLevelItem(0).text(0), 'match504.txt')
