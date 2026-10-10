"""Visible-folder updates remain bounded and retain immutable old read snapshots."""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch
from commonUtils.directory import DirectoryCache
from commonUtils.operations import OperationCancelled


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.root = base / 'files'; self.root.mkdir()
        self.child = self.root / 'child'; self.child.mkdir()
        self.deep = self.child / 'deep'; self.deep.mkdir()
        self.file = self.deep / 'file.txt'; self.file.write_bytes(b'abc')
        self.cache = DirectoryCache(database=base / 'cache' / 'index.sqlite3')
        self.addCleanup(self.cache.close)

    def test_unstable_directory_finishes_partial_instead_of_looping(self):
        identity = self.cache._folder_identity
        attempts = []
        def changing(folder, root):
            if folder == self.child:
                attempts.append(folder)
                if len(attempts) > 8:
                    raise AssertionError('Unbounded retry of a changing folder')
                return str(len(attempts))
            return identity(folder, root)
        self.cache.set_priority_folders('view', (self.child,))
        with patch.object(self.cache, '_folder_identity', side_effect=changing):
            result = self.cache.reconcile_folder(self.root, once=True)
        self.assertFalse(result.complete)
        self.assertEqual(len(attempts), 2)  # Before/after a single enumeration.
        self.assertTrue(self.cache.was_checked_this_session(self.child))
        with patch.object(self.cache, 'get', side_effect=AssertionError('Automatic full retry')):
            self.assertFalse(self.cache.reconcile_folder(self.root, once=True).complete)
        self.assertTrue(self.cache.reconcile_folder(self.root, full=True).complete)

    def test_notifications_do_not_restart_unreadable_partial_tree(self):
        scan = os.scandir
        def unreadable(path):
            if Path(path) == self.deep:
                raise PermissionError('locked')
            return scan(path)
        with patch('commonUtils.directory.os.scandir', side_effect=unreadable):
            self.assertFalse(self.cache.reconcile_folder(self.root, once=True).complete)
        added = self.child / 'added.txt'; added.write_bytes(b'12345')
        calls = []
        def recorded(path):
            calls.append(Path(path)); return scan(path)
        with patch.object(self.cache, 'get', side_effect=AssertionError('Full retry')):
            with patch('commonUtils.directory.os.scandir', side_effect=recorded):
                result = self.cache.reconcile_folder(self.root, once=True, changes=(added,))
        self.assertEqual(calls, [self.root, self.child])
        self.assertFalse(result.complete)
        self.assertEqual(result.entry(added).size, 5)
        self.assertTrue(self.cache.reconcile_folder(self.root, full=True).complete)

    def test_resumed_unchanged_index_verifies_metadata_only_once(self):
        from commonUtils.operations import OperationCancelled
        stop = [False]
        def report(done, total, message):
            if message.startswith('Checking file metadata'):
                stop[0] = True
        with self.assertRaises(OperationCancelled):
            self.cache.get(self.root, cancelled=lambda: stop[0], report=report)
        with patch.object(self.cache, '_validate', wraps=self.cache._validate) as validate:
            result = self.cache.get(self.root)
        self.assertTrue(result.complete)
        self.assertTrue(result.resumed)
        self.assertEqual(validate.call_count, 1)

    def test_index_diagnostics_are_scoped_bounded_and_read_only(self):
        scan = os.scandir
        def unreadable(path):
            if Path(path) in (self.child, self.root / 'other'):
                raise PermissionError('access denied')
            return scan(path)
        other = self.root / 'other'; other.mkdir()
        with patch('commonUtils.directory.os.scandir', side_effect=unreadable):
            self.cache.get(self.root)
        with patch.object(self.cache, '_writer', side_effect=AssertionError('Diagnostics acquired writer')):
            with patch('commonUtils.directory.os.scandir', side_effect=AssertionError('Diagnostics scanned files')):
                report = self.cache.index_issues(self.root, limit=1)
                scoped = self.cache.index_issues(self.child)
        self.assertEqual(report['total'], 2)
        self.assertEqual(len(report['rows']), 1)
        self.assertEqual(report['counts'], {'Scan error': 2})
        self.assertTrue(report['partial'])
        self.assertEqual(scoped['total'], 1)
        self.assertEqual(scoped['rows'], ((self.child, 'Scan error', 'access denied'),))
        self.assertEqual(self.cache.index_issues(self.deep)['total'], 0)
        self.cache.get(self.root)
        self.assertEqual(self.cache.index_issues(self.root)['total'], 0)

    def test_diagnostics_distinguish_unscanned_and_changed_checkpoints(self):
        self.cache.get(self.root)
        import sqlite3
        with closing(sqlite3.connect(self.cache.database)) as db, db:
            generation = db.execute('SELECT completed FROM roots').fetchone()[0]
            db.execute("UPDATE folders SET status='pending',identity=NULL WHERE generation=? AND path=?",
                       (generation, str(self.deep)))
            db.execute("UPDATE folders SET status='pending' WHERE generation=? AND path=?",
                       (generation, str(self.child)))
        report = self.cache.index_issues(self.root)
        self.assertEqual(report['counts'], {'Needs recheck': 1, 'Not fully scanned': 1})
        kinds = {path: kind for path, kind, reason in report['rows']}
        self.assertEqual(kinds[self.deep], 'Not fully scanned')
        self.assertEqual(kinds[self.child], 'Needs recheck')

    def test_verification_errors_retain_the_actual_failed_file(self):
        self.cache.get(self.root)
        lstat = Path.lstat
        def unreadable(path):
            if path == self.file:
                raise PermissionError('file metadata denied')
            return lstat(path)
        with patch.object(Path, 'lstat', unreadable):
            result = self.cache.get(self.root)
        self.assertFalse(result.complete)
        self.assertIn((self.file, 'Scan error', 'file metadata denied'),
                      self.cache.index_issues(self.root)['rows'])

    def test_failed_folder_notifications_and_parent_updates_do_not_retry_failures(self):
        scan = os.scandir
        failures = []
        def unreadable(path):
            if Path(path) == self.deep:
                failures.append(path)
                raise PermissionError('locked')
            return scan(path)
        with patch('commonUtils.directory.os.scandir', side_effect=unreadable):
            self.cache.reconcile_folder(self.root, once=True)
            for _ in range(3):
                self.cache.reconcile_folder(self.root, changes=(self.deep,))
                self.cache.reconcile_folder(self.deep, changes=(self.deep,))
            added = self.child/'healthy.txt'; added.write_bytes(b'new')
            self.cache.reconcile_folder(self.root, changes=(added,))
        self.assertEqual(len(failures), 1)
        self.assertEqual(self.cache.index_issues(self.deep)['counts'], {'Scan error': 1})
        self.assertEqual(self.cache.peek(self.root).entry(added).size, 3)
        # A restarted browser preserves failure suppression from disk while
        # resuming other unfinished work. Explicit Refresh still retries.
        with DirectoryCache(database=self.cache.database) as restarted:
            with patch('commonUtils.directory.os.scandir', side_effect=unreadable):
                self.assertFalse(restarted.reconcile_folder(self.root, once=True).complete)
                self.assertEqual(len(failures), 1)
                self.assertFalse(restarted.reconcile_folder(self.root, full=True).complete)
                self.assertEqual(len(failures), 2)
            self.assertTrue(restarted.reconcile_folder(self.root, full=True).complete)
            self.assertEqual(restarted.index_issues(self.root)['total'], 0)

    def test_completed_navigation_checks_one_folder_without_enumerating_descendants(self):
        first = self.cache.get(self.root)
        with patch.object(self.cache, '_validate', side_effect=AssertionError('Full-tree validation')):
            with patch('commonUtils.directory.os.scandir', side_effect=AssertionError('Unchanged folders enumerated')):
                checked = self.cache.reconcile_folder(self.child)
        self.assertEqual(checked.entries.generation, first.entries.generation)
        self.assertEqual(len(checked.entries), 2)
        self.assertFalse(checked.metadata_checked)
        self.assertGreater(checked.folder_stats([self.child])[self.child].scanned_at, first.scanned_at)

    def test_new_file_in_browsed_folder_updates_parent_sizes_without_copying_generation(self):
        previous = self.cache.get(self.root)
        added = self.deep / 'added.txt'; added.write_bytes(b'12345')
        calls = []; scan = os.scandir
        def scandir(path):
            calls.append(Path(path)); return scan(path)
        with patch('commonUtils.directory.os.scandir', side_effect=scandir):
            fresh = self.cache.reconcile_folder(self.deep)
        self.assertEqual(calls, [self.deep])
        self.assertEqual(fresh.entries.generation, previous.entries.generation)
        self.assertEqual(fresh.entry(added).size, 5)
        self.assertIsNone(previous.entry(added))
        self.assertEqual(previous.folder_stats()[self.root].size, 3)
        self.assertEqual(self.cache.peek(self.root).folder_stats()[self.root].size, 8)

    def test_notification_detects_in_place_file_write_without_directory_mtime_change(self):
        self.cache.get(self.root)
        self.file.write_bytes(b'longer data')
        fresh = self.cache.reconcile_folder(self.root, changes=(self.file,))
        self.assertEqual(fresh.entry(self.file).size, 11)
        self.assertEqual(fresh.folder_stats()[self.root].size, 11)

    def test_new_branch_is_discovered_and_deleted_branch_is_removed(self):
        self.cache.get(self.root)
        new = self.child / 'new'; new.mkdir(); (new / 'nested').mkdir()
        added = new / 'nested' / 'file.txt'; added.write_bytes(b'new')
        fresh = self.cache.reconcile_folder(self.child)
        self.assertIsNotNone(fresh.entry(added))
        added.unlink(); (new / 'nested').rmdir(); new.rmdir()
        fresh = self.cache.reconcile_folder(self.child)
        self.assertIsNone(fresh.entry(added))
        self.assertTrue(fresh.complete)

    def test_cancelled_incremental_update_preserves_preexisting_index(self):
        first = self.cache.get(self.root)
        added = self.child / 'added.txt'; added.write_bytes(b'new')
        stop = [False]
        def report(done, total, message):
            if message.startswith('Indexing '): stop[0] = True
        with self.assertRaises(OperationCancelled):
            self.cache.reconcile_folder(self.child, cancelled=lambda: stop[0], report=report)
        saved = self.cache.peek(self.root)
        self.assertIsNone(saved.entry(added))
        self.assertEqual(saved.folder_stats()[self.root].size, first.folder_stats()[self.root].size)
        self.assertIsNotNone(self.cache.reconcile_folder(self.child).entry(added))

    def test_missing_index_uses_resumable_initial_scan(self):
        with patch.object(self.cache, 'get', wraps=self.cache.get) as get:
            self.assertTrue(self.cache.reconcile_folder(self.root).complete)
        get.assert_called_once()

    def test_visiting_new_unindexed_directory_discovers_missing_parent_branch(self):
        self.cache.get(self.root)
        branch = self.child / 'new' / 'nested'; branch.mkdir(parents=True)
        added = branch / 'added.txt'; added.write_bytes(b'12345')
        fresh = self.cache.reconcile_folder(branch)
        self.assertEqual(fresh.folder_stats()[branch].size, 5)
        self.assertTrue(fresh.complete)
        self.assertTrue(fresh.folder_stats()[branch].complete)
        saved = self.cache.peek(self.root)
        self.assertEqual(saved.folder_stats()[self.root].size, 8)
        self.assertIsNotNone(saved.entry(branch))
        self.assertIsNotNone(saved.entry(added))

    def test_removed_watched_branch_does_not_reappear_as_an_error(self):
        self.cache.get(self.root)
        self.file.unlink(); self.deep.rmdir()
        fresh = self.cache.reconcile_folder(self.child, changes=(self.deep,))
        self.assertTrue(fresh.complete)
        self.assertNotIn(self.deep, fresh.folder_stats())
        self.assertFalse(fresh.errors)

    def test_repeated_updates_prune_retired_metadata_but_keep_old_readers(self):
        previous = self.cache.get(self.root)
        for size in range(4, 14):
            self.file.write_bytes(b'x' * size)
            self.cache.reconcile_folder(self.deep)
        self.assertEqual(previous.entry(self.file).size, 3)
        with self.cache._writer(lambda: False) as db:
            records = db.execute('SELECT count(*) FROM entry_records').fetchone()[0]
            referenced = db.execute('SELECT count(DISTINCT record_id) FROM generation_entries').fetchone()[0]
            self.assertEqual(records, referenced)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())

    def test_deep_refresh_updates_borrowed_generation_and_ancestor_totals(self):
        before = self.cache.get(self.root)
        added = self.deep / 'added.txt'; added.write_bytes(b'12345')
        fresh = self.cache.reconcile_folder(self.child, full=True)
        self.assertTrue(fresh.metadata_checked)
        self.assertEqual(fresh.entries.generation, before.entries.generation)
        self.assertIsNotNone(fresh.entry(added))
        self.assertEqual(self.cache.peek(self.root).folder_stats()[self.root].size, 8)

    def test_deep_refresh_handles_removed_descendants_without_phantom_errors(self):
        self.cache.get(self.root)
        self.file.unlink(); self.deep.rmdir()
        fresh = self.cache.reconcile_folder(self.root, full=True)
        self.assertTrue(fresh.complete)
        self.assertFalse(fresh.errors)
        self.assertNotIn(self.deep, fresh.folder_stats())

    def test_session_revisit_skips_writer_but_notifications_and_restart_recheck(self):
        self.cache.get(self.root)
        self.cache.reconcile_folder(self.deep, once=True)
        with patch.object(self.cache, '_writer', side_effect=AssertionError('Revisit acquired writer')):
            self.cache.reconcile_folder(self.deep, once=True)
        self.file.write_bytes(b'longer data')
        changed = self.cache.reconcile_folder(self.deep, once=True, changes=(self.file,))
        self.assertEqual(changed.entry(self.file).size, 11)
        with DirectoryCache(database=self.cache.database) as restarted:
            self.file.write_bytes(b'new')
            self.assertEqual(restarted.reconcile_folder(self.deep, once=True).entry(self.file).size, 3)

    def test_initial_scan_prioritizes_missing_ancestors_and_visible_contents(self):
        earlier = self.root / 'a-first'; earlier.mkdir(); (earlier / 'file.txt').write_bytes(b'x')
        owner = object(); self.cache.set_priority_folders(owner, (self.deep,))
        scanned = []; original = self.cache._scan_folder
        def scan(*args, **kwargs):
            scanned.append(args[4]); return original(*args, **kwargs)
        with patch.object(self.cache, '_scan_folder', side_effect=scan):
            saved = self.cache.get(self.root)
        self.assertTrue(saved.complete)
        self.assertLess(scanned.index(self.deep), scanned.index(earlier))
        self.assertTrue(self.cache.was_checked_this_session(self.deep))
        self.cache.set_priority_folders(owner)
        self.assertFalse(self.cache._priority_folders)
