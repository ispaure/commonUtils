"""Browser subscriptions share work, progress, and independent cancellation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from threading import Event
from tempfile import TemporaryDirectory
from time import monotonic,sleep
import unittest
from unittest.mock import patch
from commonUtils.directory_index import DirectoryCache
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.index_worker import FolderOperation


class SharedJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=qt.QApplication.instance() or qt.QApplication([])

    def wait(self,condition):
        deadline=monotonic()+5
        while not condition():
            self.assertLess(monotonic(),deadline)
            self.app.processEvents();sleep(.005)
        self.app.processEvents()

    def test_same_location_runs_once_and_one_tab_cancels_without_stopping_other(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);cache=DirectoryCache(database=root/'index.sqlite3')
            entered=Event();release=Event();calls=[];cancelled=[]
            def scanner(root,stop,**kwargs):
                calls.append(root);entered.set()
                kwargs['report'](5,0,f'Indexing {root} · 5 entries in this folder')
                while not release.wait(.01):
                    if stop():cancelled.append(True);return None
                return {}
            with patch('commonUtils.ui.file_browser.index_worker.directory_cache',cache):
                first=FolderOperation(root,scanner,self.app);second=FolderOperation(root,scanner,self.app)
                done=[];messages=[]
                first.finished.connect(lambda:done.append('first'))
                second.finished.connect(lambda:done.append('second'))
                second.progress.connect(messages.append)
                first.start();self.wait(entered.is_set);second.start()
                self.assertIs(first._job,second._job)
                first.requestInterruption();self.wait(lambda:'first' in done)
                self.assertFalse(cancelled)
                self.assertTrue(any('entries' in text and '/s' in text for text in messages))
                release.set();self.wait(lambda:'second' in done)
                self.assertEqual(calls,[root]);self.assertFalse(cancelled)
                first.deleteLater();second.deleteLater()

    def test_cancel_after_worker_exit_before_queued_finish_completes_handle(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            cache = DirectoryCache(database=root/'index.sqlite3')
            with patch('commonUtils.ui.file_browser.index_worker.directory_cache', cache):
                handle = FolderOperation(root, lambda *args, **kwargs: {}, self.app)
                handle.start()
                job = handle._job
                self.assertTrue(job.wait(5000))  # Do not deliver queued GUI callbacks yet.
                self.assertFalse(handle.isFinished())
                handle.requestInterruption()
                self.wait(handle.isFinished)
                self.assertFalse(handle.isRunning())
                handle.deleteLater()

    def test_last_subscriber_cancels_and_waits_for_its_worker(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);cache=DirectoryCache(database=root/'index.sqlite3')
            entered=Event();stopped=Event()
            def scanner(root,stop,**kwargs):
                entered.set()
                while not stop():sleep(.005)
                stopped.set();return None
            with patch('commonUtils.ui.file_browser.index_worker.directory_cache',cache):
                handle=FolderOperation(root,scanner,self.app)
                handle.start();self.wait(entered.is_set)
                handle.requestInterruption();handle.wait()
                self.assertTrue(stopped.is_set())
                self.wait(lambda:handle._finished)
                handle.deleteLater()

    def test_destroyed_subscriber_does_not_leave_an_orphaned_worker(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);cache=DirectoryCache(database=root/'index.sqlite3')
            entered=Event();stopped=Event()
            def scanner(root,stop,**kwargs):
                entered.set()
                while not stop():sleep(.005)
                stopped.set();return None
            with patch('commonUtils.ui.file_browser.index_worker.directory_cache',cache):
                handle=FolderOperation(root,scanner,self.app)
                handle.start();self.wait(entered.is_set)
                handle.deleteLater()
                self.app.sendPostedEvents(None,qt.QEvent.Type.DeferredDelete)
                self.wait(stopped.is_set)

    def test_saved_count_is_reported_before_loading_totals_and_separate_from_run_count(self):
        from commonUtils.directory_index import Snapshot
        from commonUtils.ui.file_browser.index_worker import _IndexJob
        with TemporaryDirectory() as folder:
            base=Path(folder);root=base/'files';root.mkdir();(root/'file.txt').write_text('abc')
            cache=DirectoryCache(database=base/'cache'/'index.sqlite3');cache.get(root)
            messages=[];read=Snapshot.folder_stats
            def totals(snapshot,*args,**kwargs):
                self.assertIn('1 saved entries',messages[-1])
                self.assertEqual(kwargs['children_of'], root)
                return read(snapshot,*args,**kwargs)
            with patch('commonUtils.ui.file_browser.index_worker.directory_cache',cache):
                job=_IndexJob(root,lambda *args,**kwargs:None,self.app)
                job.progress.connect(messages.append)
                with patch.object(Snapshot,'folder_stats',totals):job._cached(force=True)
                job._report(2,0,f'Indexing {root} · 2 entries in this folder')
                self.assertIn('1 saved entries',messages[-1])
                self.assertIn('2 processed this run',messages[-1])
                job.deleteLater()

    def test_deep_refresh_never_joins_an_immediate_folder_check(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); cache = DirectoryCache(database=root / 'index.sqlite3')
            release = Event(); calls = []
            def scanner(root, stop, **kwargs):
                calls.append(root)
                while not release.wait(.01):
                    if stop(): return None
                return {}
            with patch('commonUtils.ui.file_browser.index_worker.directory_cache', cache):
                first = FolderOperation(root, scanner, self.app, request_key=('reconcile', ()))
                second = FolderOperation(root, scanner, self.app, request_key=('full', ()))
                try:
                    first.start(); second.start()
                    self.wait(lambda: len(calls) == 2)
                    self.assertIsNot(first._job, second._job)
                finally:
                    release.set()
                    self.wait(lambda: first.isFinished() and second.isFinished())
                    first.deleteLater(); second.deleteLater()

    def test_descendant_view_joins_reconcile_scan_without_starting_another_scanner(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); child = root / 'child'; child.mkdir()
            cache = DirectoryCache(database=root / 'index.sqlite3')
            entered, release = Event(), Event(); calls = []
            def scanner(root, stop, **kwargs):
                calls.append(root); entered.set()
                while not release.wait(.01):
                    if stop(): return None
                return {}
            with patch('commonUtils.ui.file_browser.index_worker.directory_cache', cache):
                first = FolderOperation(root, scanner, self.app, request_key=('reconcile', (root,)))
                second = FolderOperation(child, scanner, self.app, request_key=('reconcile', ()))
                try:
                    first.start(); self.wait(entered.is_set); second.start()
                    self.assertIs(first._job, second._job)
                    self.assertEqual(second.root, root)
                    self.assertEqual(second.visible_root, child)
                    first.requestInterruption(); self.wait(first.isFinished)
                    self.assertFalse(second._job.isInterruptionRequested())
                finally:
                    release.set()
                    self.wait(lambda: first.isFinished() and second.isFinished())
                    first.deleteLater(); second.deleteLater()
            self.assertEqual(calls, [root])
