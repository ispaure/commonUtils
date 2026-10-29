"""Browser subscriptions follow shared jobs under cache-first policy."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import sqlite3
from time import monotonic, sleep
import unittest
from unittest.mock import patch

from commonUtils.filesystem.index import DirectoryCache
from commonUtils.filesystem.index.coordinator import IndexCoordinator, _retry_sql
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from commonUtils.ui.file_browser.index_policy import IndexPolicy


class SharedBrowserTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base/'files'
        self.root.mkdir()
        self.child = self.root/'child'
        self.child.mkdir()
        (self.child/'old.txt').write_text('old')
        self.cache = DirectoryCache(database=self.base/'cache'/'index.sqlite3')
        with self.cache.get(self.root):
            pass
        self.queue = IndexCoordinator(self.cache)
        self.cache.coordinator = self.queue
        self.stop = Event()
        self.browsers = []
        self.worker = None
        self.patches = [patch(name, self.cache) for name in (
            'commonUtils.filesystem.index.directory_cache',
            'commonUtils.ui.file_browser.index_worker.directory_cache',
            'commonUtils.ui.file_browser.index_search.directory_cache',
            'commonUtils.ui.file_browser.discovery.directory_cache')]
        self.patches.append(patch('commonUtils.ui.file_browser.index_policy.index_policy',
                                  return_value=IndexPolicy(scan_on_open=False, watch_changes=False)))
        for item in self.patches:
            item.start()

    def tearDown(self):
        for browser in self.browsers:
            browser.shutdown()
        self.stop.set()
        if self.worker is not None:
            self.worker.join(10)
            self.assertFalse(self.worker.is_alive())
        self.app.processEvents()
        for item in reversed(self.patches):
            item.stop()
        self.cache.close()
        self.temp.cleanup()

    def wait(self, predicate):
        deadline = monotonic()+10
        while True:
            value = _retry_sql(predicate, cancelled=lambda: monotonic() >= deadline)
            if value:
                self.app.processEvents()
                return value
            self.assertLess(monotonic(), deadline)
            self.app.processEvents()
            sleep(.01)

    def browser(self, root):
        browser = FileBrowser(root)
        self.browsers.append(browser)
        browser.show()
        return browser

    def test_cached_child_follows_parent_and_receives_updated_totals(self):
        # Leave an older independently indexed child to catch accidental reads
        # from that child instead of the parent's freshly published generation.
        with self.cache.get(self.child):
            pass
        identity = self.queue.submit(self.root, full=True)
        browser = self.browser(self.child)
        self.wait(lambda: 'File index' in browser.index_status.text())
        self.assertTrue(browser.folder_busy)
        self.assertFalse(browser._loading_cached_only)
        (self.child/'new.txt').write_text('new data')
        self.worker = Thread(target=self.queue.run, args=(self.stop.is_set,))
        self.worker.start()
        self.wait(lambda: self.queue.status(identity)['state'] == 'done' and not browser.folder_busy)
        self.assertEqual(browser.model.folder_totals[self.child].files, 2)
        with self.cache.peek(self.child) as snapshot:
            self.assertEqual(snapshot.folder_stats([self.child])[self.child].files, 2)

    def test_idle_browser_observes_job_started_later_without_creating_another(self):
        class Activity(qt.QObject):
            changed = qt.Signal(object)
        activity = Activity()
        self.cache.shared_activity = activity.changed
        self.queue.notify = activity.changed.emit
        browser = self.browser(self.child)
        self.wait(lambda: not browser.folder_busy)
        identity = self.queue.submit(self.root, full=True)
        (self.child/'later.txt').write_text('changed in another instance')
        self.worker = Thread(target=self.queue.run, args=(self.stop.is_set,))
        self.worker.start()
        self.wait(lambda: browser.model.folder_totals.get(self.child) is not None
                  and browser.model.folder_totals[self.child].files == 2 and not browser.folder_busy)
        self.wait(lambda: self.queue.status(identity)['state'] == 'done')
        def receipt_count():
            with self.queue._connection() as db:
                return db.execute('SELECT count(*) FROM jobs').fetchone()
        self.assertEqual(self.wait(receipt_count)[0], 1)

    def test_pausing_a_view_detaches_without_cancelling_durable_request(self):
        identity = self.queue.submit(self.root, full=True)
        first = self.browser(self.root)
        second = self.browser(self.root)
        self.wait(lambda: first.folder_busy and second.folder_busy and not first._loading_cached_only)
        first._toggle_index_pause()
        self.wait(lambda: first._index_paused and not first.folder_busy)
        self.assertTrue(second.folder_busy)
        self.assertEqual(self.wait(lambda: self.queue.status(identity))['state'], 'pending')
        self.worker = Thread(target=self.queue.run, args=(self.stop.is_set,))
        self.worker.start()
        self.wait(lambda: not second.folder_busy)
        self.wait(lambda: self.queue.status(identity)['state'] == 'done')

    def test_receipt_poll_waits_for_a_real_queue_writer_lock(self):
        identity = self.queue.submit(self.root)
        entered, release = Event(), Event()
        def writer():
            with self.queue._connection() as db:
                db.execute('BEGIN EXCLUSIVE')
                entered.set()
                release.wait(10)
        worker = Thread(target=writer)
        worker.start()
        attempts = []
        def receipt():
            attempts.append(None)
            try:
                return self.queue.status(identity)
            except sqlite3.OperationalError:
                # Keep the real writer lock until the reader observes it;
                # elapsed timers can fire before a busy CI reader is scheduled.
                release.set()
                raise
        try:
            self.assertTrue(entered.wait(3))
            job = self.wait(receipt)
            self.assertEqual(job['state'], 'pending')
            self.assertGreater(len(attempts), 1)
        finally:
            release.set()
            worker.join(5)
            self.assertFalse(worker.is_alive())


if __name__ == '__main__':
    unittest.main()
