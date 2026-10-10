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

    def test_unchanged_totals_and_cache_notifications_do_not_reload_details(self):
        self.wait(lambda: not self.browser.busy)
        totals = self.browser.model.folder_totals
        with patch.object(self.browser, 'load', wraps=self.browser.load) as load:
            self.browser._folders_progressed(self.root, totals)
            self.browser._folders_loaded(self.root, totals)
            self.assertEqual(load.call_count, 0)
        pending = self.browser._reconcile_pending
        changes = set(self.browser._changed_paths)
        self.browser._indexed_path_changed(str(self.cache.database))
        self.assertEqual(self.browser._reconcile_pending, pending)
        self.assertEqual(self.browser._changed_paths, changes)

    def test_index_progress_does_not_load_a_disabled_preview(self):
        from dataclasses import replace
        self.browser.preview_toggle.setChecked(False)
        self.browser.views.select_source(self.browser.model.index(str(self.child)))
        self.wait(lambda: not self.browser.busy)
        self.assertEqual(self.browser.selected_object.path, self.child)
        totals = dict(self.browser.model.folder_totals)
        totals[self.child] = replace(totals[self.child], size=totals[self.child].size + 1)
        with patch.object(self.browser, 'load', side_effect=AssertionError('Disabled preview was loaded')):
            self.browser._folders_progressed(self.root, totals)

    def test_index_progress_does_not_replace_a_pending_selection_change(self):
        from dataclasses import replace
        self.browser.preview_toggle.setChecked(True)
        self.browser.views.select_source(self.browser.model.index(str(self.child)))
        self.wait(lambda: not self.browser.busy)
        self.browser.refresh_pending = True
        totals = dict(self.browser.model.folder_totals)
        totals[self.child] = replace(totals[self.child], size=totals[self.child].size + 1)
        with patch.object(self.browser, 'load', side_effect=AssertionError('Pending selection was replaced')):
            self.browser._folders_progressed(self.root, totals)
        self.browser.refresh_pending = False


    def test_partial_scan_stops_and_notifications_do_not_start_another_full_run(self):
        self.unwatch()
        self.cache.clear(self.root)
        scan = os.scandir
        def unreadable(path):
            if Path(path) == self.deep:
                raise PermissionError('locked')
            return scan(path)
        with patch('commonUtils.directory_index.os.scandir', side_effect=unreadable):
            with patch.object(self.cache, 'get', wraps=self.cache.get) as get:
                self.browser.refresh()
                self.wait(lambda: not self.browser.folder_busy)
                self.assertEqual(get.call_count, 1)
                self.assertIn('incomplete', self.browser.index_status.text().lower())
                self.assertNotIn(str(self.deep), self.browser.index_watcher.directories())
                self.assertFalse(self.browser.index_details_button.isHidden())
                self.browser.index_details_button.click()
                dialog = self.browser._index_details_dialog
                self.wait(lambda: dialog.results.topLevelItemCount() > 0)
                self.assertIn('scan error', dialog.summary.text())
                self.assertEqual(dialog.results.topLevelItem(0).data(1, qt.Qt.ItemDataRole.UserRole), self.deep)
                self.assertIn('locked', dialog.results.topLevelItem(0).text(2))
                self.assertNotIn(str(self.deep), self.browser.index_status.text())
                dialog.close()
                self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
                self.assertIsNone(self.browser._index_details_dialog)
                self.unwatch()
                added = self.child / 'new.txt'; added.write_bytes(b'12345')
                self.browser._indexed_path_changed(str(added))
                self.wait(lambda: not self.browser.folder_busy and
                          self.cache.peek(self.root).entry(added) is not None)
                self.assertEqual(get.call_count, 1)
                self.assertFalse(self.browser.reconcile_timer.isActive())
                self.assertTrue(self.browser.index_activity.isHidden())

    def test_failed_folder_is_unwatched_and_queued_notifications_never_retry_it(self):
        self.unwatch(); self.cache.clear(self.root)
        scan = os.scandir; attempts = []
        def unreadable(path):
            if Path(path) == self.child:
                attempts.append(path)
                raise PermissionError('locked')
            return scan(path)
        with patch('commonUtils.directory_index.os.scandir', side_effect=unreadable):
            self.browser.refresh(); self.wait(lambda: not self.browser.folder_busy)
            self.assertNotIn(str(self.child), self.browser.index_watcher.directories())
            for _ in range(3):
                self.browser._indexed_path_changed(str(self.child))
                self.wait(lambda: not self.browser.reconcile_debounce.isActive() and not self.browser.folder_busy)
            self.assertEqual(len(attempts), 1)
            self.assertFalse(self.browser.index_details_button.isHidden())
            self.browser.refresh(); self.wait(lambda: not self.browser.folder_busy)
            self.assertEqual(len(attempts), 2)

    def test_completed_scan_has_no_polling_or_pause_control(self):
        self.assertFalse(self.browser.reconcile_timer.isActive())
        self.assertTrue(self.browser.index_pause_button.isHidden())
        self.assertIn('checked', self.browser.index_status.text().lower())

    def test_first_visit_checks_and_reopening_reuses_index_until_refresh(self):
        self.unwatch()
        added = self.child / 'added.txt'; added.write_bytes(b'12345')
        with patch.object(self.cache, '_validate', side_effect=AssertionError('Whole-tree validation')):
            self.browser.navigate(self.child)
            self.wait(lambda: not self.browser.folder_busy)
            self.assertEqual(self.browser.model.folder_totals[self.child].size, 8)
            self.unwatch()
            second = self.child / 'second.txt'; second.write_bytes(b'xx')
            with patch('commonUtils._directory_reconcile._changed', side_effect=AssertionError('Revisit rechecked metadata')):
                self.browser.navigate(self.child)
                self.wait(lambda: not self.browser.folder_busy)
            self.assertEqual(self.browser.model.folder_totals[self.child].size, 8)
        self.assertIsNone(self.cache.peek(self.root).entry(second))
        self.wait(lambda: self.browser.model.index(str(second)).isValid())
        self.browser.refresh()
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

    def test_navigation_prioritizes_visible_folder_without_interrupting_initial_scan(self):
        from threading import Event
        self.unwatch(); self.cache.clear()
        earlier = self.root / 'a-first'; earlier.mkdir()
        (earlier / 'file.txt').write_bytes(b'x')
        entered, release = Event(), Event()
        scanned = []; original = self.cache._scan_folder
        def scan(*args, **kwargs):
            result = original(*args, **kwargs)
            scanned.append(args[4])
            if args[4] == self.root:
                entered.set()
                while not release.wait(.01):
                    if args[5](): break
            return result
        with patch.object(self.cache, '_scan_folder', side_effect=scan):
            try:
                # Restart the cleared index explicitly: revisiting an unchanged
                # folder deliberately does not scan, and watcher timing varies.
                self.browser.refresh_folder_totals()
                self.wait(entered.is_set)
                operation = self.browser.folder_operation
                job = operation._job
                self.browser.navigate(self.deep)
                self.assertIs(self.browser.folder_operation, operation)
                self.assertIs(operation._job, job)
                self.assertFalse(operation.isInterruptionRequested())
                self.assertEqual(operation.root, self.root)
                self.assertEqual(operation.visible_root, self.deep)
                release.set()
                self.wait(lambda: not self.browser.folder_busy)
                self.assertLess(scanned.index(self.deep), scanned.index(earlier))
                self.assertEqual(self.browser.model.folder_totals[self.deep].size, 3)
                self.assertTrue(self.cache.was_checked_this_session(self.deep))
                self.assertEqual(self.cache.peek(self.deep).entries.generation,
                                 self.cache.peek(self.root).entries.generation)
            finally:
                release.set()
        with self.cache._writer(lambda: False) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM roots').fetchone()[0], 1)
        self.browser.close()
        self.wait(lambda: not self.browser.folder_busy)
        self.assertNotIn(self.browser._index_priority_owner, self.cache._priority_folders)

    def test_second_open_view_gets_prioritized_sizes_before_initial_scan_finishes(self):
        from threading import Event
        self.unwatch(); self.cache.clear()
        earlier = self.root / 'a-first'; earlier.mkdir(); (earlier / 'file.txt').write_bytes(b'x')
        entered, release_root, tail_entered, release_tail = Event(), Event(), Event(), Event()
        original = self.cache._scan_folder
        def scan(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[4] in (self.root, earlier):
                event, release = (entered,release_root) if args[4] == self.root else (tail_entered,release_tail)
                event.set()
                while not release.wait(.01):
                    if args[5](): break
            return result
        second = None
        with patch.object(self.cache, '_scan_folder', side_effect=scan):
            try:
                self.browser.refresh_folder_totals(); self.wait(entered.is_set)
                second = FileBrowser(self.deep); second.show()
                self.assertIs(second.folder_operation._job, self.browser.folder_operation._job,
                              (second.folder_operation.request_key, self.browser.folder_operation.request_key,
                               self.browser.folder_operation.isInterruptionRequested(),
                               self.browser.folder_root, self.browser._changed_paths))
                release_root.set(); self.wait(tail_entered.is_set)
                self.wait(lambda: self.deep in second.model.folder_totals and
                          second.model.folder_totals[self.deep].size == 3)
                self.assertTrue(self.browser.folder_busy)
                self.assertTrue(second.folder_busy)
                release_tail.set()
                self.wait(lambda: not self.browser.folder_busy and not second.folder_busy)
            finally:
                release_root.set(); release_tail.set()
                if second is not None:
                    second.close(); self.wait(lambda: not second.folder_busy)
