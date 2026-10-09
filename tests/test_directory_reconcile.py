"""Visible-folder updates remain bounded and retain immutable old read snapshots."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch
from commonUtils.directory_index import DirectoryCache
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

    def test_completed_navigation_checks_one_folder_without_enumerating_descendants(self):
        first = self.cache.get(self.root)
        with patch.object(self.cache, '_validate', side_effect=AssertionError('Full-tree validation')):
            with patch('commonUtils.directory_index.os.scandir', side_effect=AssertionError('Unchanged folders enumerated')):
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
        with patch('commonUtils.directory_index.os.scandir', side_effect=scandir):
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
