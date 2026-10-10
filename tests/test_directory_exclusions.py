"""Synthetic macOS firmlink layout: never traverse the Data alias from /."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

from commonUtils.directory_index import DirectoryCache, storage_totals
from commonUtils.operations import OperationCancelled


class MacOSExclusionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / 'disk'
        self.data = self.root / 'System' / 'Volumes' / 'Data'
        self.data.mkdir(parents=True)
        users = self.root / 'Users'
        users.mkdir()
        (users / 'file').write_bytes(b'12345')
        (self.data / 'duplicate').write_bytes(b'12345')
        self.cache = DirectoryCache(database=base / 'cache' / 'index.sqlite3')
        self.addCleanup(self.cache.close)

    @contextmanager
    def macos(self):
        with patch('commonUtils._directory_exclusions.sys.platform', 'darwin'), \
             patch('commonUtils._directory_exclusions.MACOS_ROOT', self.root), \
             patch('commonUtils._directory_exclusions.MACOS_DATA', self.data):
            yield

    def assert_clean(self, snapshot):
        self.assertEqual(storage_totals(snapshot)[self.root], 5)
        self.assertFalse(any(entry.path == self.data or self.data in entry.path.parents
                             for entry in snapshot.entries))

    def test_discovery_skips_alias_but_explicit_data_scope_works(self):
        scan = os.scandir
        def guarded(path):
            self.assertNotEqual(Path(path), self.data)
            return scan(path)
        with self.macos():
            with patch('commonUtils._directory_store.os.scandir', side_effect=guarded):
                self.assert_clean(self.cache.get(self.root))
            explicit = self.cache.reconcile_folder(self.data)
            self.assertEqual(storage_totals(explicit)[self.data], 5)
            self.assert_clean(self.cache.get(self.root))

    def test_completed_cache_repaired_without_full_enumeration(self):
        with patch('commonUtils._directory_exclusions.sys.platform', 'linux'):
            old = self.cache.get(self.root)
        self.assertEqual(storage_totals(old)[self.root], 10)
        with self.macos(), patch('commonUtils._directory_store.os.scandir',
                                 side_effect=AssertionError('Unnecessary enumeration')):
            self.assert_clean(self.cache.get(self.root))
        self.assertEqual(storage_totals(old)[self.root], 10)  # Existing read transaction.
        self.assert_clean(self.cache.peek(self.root))

    def test_cache_first_repair_does_not_resume_partial_scan_or_walk_files(self):
        with patch('commonUtils._directory_exclusions.sys.platform', 'linux'):
            old = self.cache.get(self.root)
        with self.cache._writer(lambda: False) as db:
            db.execute('UPDATE roots SET building=completed,completed=NULL WHERE root=?', (str(self.root),))
            db.execute("UPDATE folders SET status='pending' WHERE generation=? AND path=?", (old.entries.generation, str(self.root)))
            db.commit()
        with self.macos(), patch('commonUtils._directory_store.os.scandir',
                                 side_effect=AssertionError('Cache repair must not enumerate folders')):
            self.cache.repair_cached_exclusions(self.root)
            self.assert_clean(self.cache.peek(self.root))
            self.assertIsNotNone(self.cache.status(self.root))
            self.assertGreater(self.cache.status(self.root)['folders_remaining'], 0)
        self.assertEqual(storage_totals(old)[self.root], 10)

    def test_cache_first_repair_cancellation_can_be_retried(self):
        with patch('commonUtils._directory_exclusions.sys.platform', 'linux'):
            self.cache.get(self.root)
        with self.macos(), patch.object(self.cache, '_publish_totals', side_effect=OperationCancelled):
            with self.assertRaises(OperationCancelled):
                self.cache.repair_cached_exclusions(self.root)
        self.assertEqual(storage_totals(self.cache.peek(self.root))[self.root], 10)
        with self.macos():
            self.cache.repair_cached_exclusions(self.root)
        self.assert_clean(self.cache.peek(self.root))

    def test_sqlite_interrupted_cleanup_rolls_back_without_masking_cancellation(self):
        for number in range(3000):
            (self.data / f'file{number}').write_bytes(b'x')
        with patch('commonUtils._directory_exclusions.sys.platform', 'linux'):
            self.cache.get(self.root)
        stop = [False]
        def report(done, total, message):
            if message.startswith('Removing saved duplicate'):
                stop[0] = True
        with self.macos():
            with self.assertRaises(OperationCancelled):
                self.cache.repair_cached_exclusions(self.root, cancelled=lambda: stop[0], report=report)
            self.assertEqual(storage_totals(self.cache.peek(self.root))[self.root], 3010)
            self.cache.repair_cached_exclusions(self.root)
        self.assert_clean(self.cache.peek(self.root))

    def test_reconciliation_repairs_saved_ancestor_totals(self):
        with patch('commonUtils._directory_exclusions.sys.platform', 'linux'):
            self.cache.get(self.root)
        with self.macos():
            self.cache.reconcile_folder(self.root / 'Users', full=True)
        self.assert_clean(self.cache.peek(self.root))

    def test_saved_descendant_seed_does_not_reintroduce_alias(self):
        self.cache.get(self.root / 'System')
        with self.macos():
            self.assert_clean(self.cache.get(self.root))

    def test_repair_preserves_independent_data_cache(self):
        with patch('commonUtils._directory_exclusions.sys.platform', 'linux'):
            self.cache.get(self.data)
            self.cache.get(self.root)
        with self.macos():
            self.assert_clean(self.cache.get(self.root))
        explicit = self.cache.peek(self.data)
        self.assertEqual(storage_totals(explicit)[self.data], 5)
        self.assertEqual(explicit.entry(self.data / 'duplicate').size, 5)

    def test_partial_scan_resume_removes_previously_saved_alias(self):
        stop = [False]
        original = self.cache._scan_folder
        def scan(*args, **kwargs):
            original(*args, **kwargs)
            if args[4] == self.data:
                stop[0] = True
        with patch('commonUtils._directory_exclusions.sys.platform', 'linux'), \
             patch.object(self.cache, '_scan_folder', side_effect=scan):
            with self.assertRaises(OperationCancelled):
                self.cache.get(self.root, cancelled=lambda: stop[0])
        self.assertIsNotNone(self.cache.peek(self.root).entry(self.data / 'duplicate'))
        with self.macos():
            self.assert_clean(self.cache.get(self.root))

    def test_cancelled_repair_retains_old_entries_and_totals(self):
        with patch('commonUtils._directory_exclusions.sys.platform', 'linux'):
            self.cache.get(self.root)
        with self.macos(), patch.object(self.cache, '_publish_totals', side_effect=OperationCancelled):
            with self.assertRaises(OperationCancelled):
                self.cache.get(self.root)
        snapshot = self.cache.peek(self.root)
        self.assertEqual(storage_totals(snapshot)[self.root], 10)
        self.assertIsNotNone(snapshot.entry(self.data / 'duplicate'))
