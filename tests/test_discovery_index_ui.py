"""Storage communicates saved checkpoints and supports rebuilding."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from time import monotonic, sleep
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch

from commonUtils.directory_index import DirectoryCache
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.storage import StorageDialog


class DiscoveryIndexUiTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name).resolve()
        self.root = folder / 'files'; self.root.mkdir()
        (self.root / 'nested').mkdir()
        (self.root / 'nested' / 'file.txt').write_text('contents')
        self.cache = DirectoryCache(database=folder / 'support' / 'index.sqlite3')
        self.addCleanup(self.cache.close)
        self.patch = patch('commonUtils.ui.file_browser.discovery.directory_cache', self.cache)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.browser = qt.QWidget()
        self.browser.navigation = SimpleNamespace(directory=self.root)
        self.addCleanup(self.browser.deleteLater)

    def dialog(self, kind=StorageDialog):
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
