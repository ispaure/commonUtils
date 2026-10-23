"""Writer operations isolate transient state while retaining durable snapshots."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.filesystem.index import DirectoryCache
from commonUtils.runtime.operations import OperationCancelled


class IndexOperationStateTests(unittest.TestCase):
    def test_cancelled_scan_releases_state_and_next_root_starts_clean(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            first, second = base / 'first', base / 'second'
            for root in (first, second):
                root.mkdir()
                (root / 'file.txt').write_bytes(b'contents')
            with DirectoryCache(database=base / 'cache' / 'index.sqlite3') as cache:
                operations = []
                def cancel_after_entry(done, total, message):
                    if message.startswith('Indexing '):
                        operations.append(cache.active_operation)
                        raise OperationCancelled('fixture cancelled')
                with self.assertRaises(OperationCancelled):
                    cache.get(first, report=cancel_after_entry)
                self.assertIsNone(cache.active_operation)
                def observe(done, total, message):
                    if message.startswith('Indexing '):
                        operations.append(cache.active_operation)
                with cache.get(second, report=observe) as snapshot:
                    self.assertTrue(snapshot.complete)
                    self.assertEqual(snapshot.folder_stats()[second].files, 1)
                self.assertIsNone(cache.active_operation)
                self.assertIsNot(operations[0], operations[-1])
                self.assertEqual(operations[-1].discovered_entries, 1)

    def test_reconciliation_uses_new_state_and_preserves_existing_reader(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / 'files'
            root.mkdir()
            path = root / 'file.txt'
            path.write_bytes(b'old')
            with DirectoryCache(database=base / 'cache' / 'index.sqlite3') as cache:
                old = cache.get(root)
                self.assertIsNone(cache.active_operation)
                path.write_bytes(b'new contents')
                operations = []
                def observe(done, total, message):
                    if message.startswith('Indexing '):
                        operations.append(cache.active_operation)
                with cache.reconcile_folder(root, changes=(path,), report=observe) as new:
                    self.assertEqual(new.folder_stats()[root].size, len(b'new contents'))
                self.assertEqual(old.folder_stats()[root].size, len(b'old'))
                self.assertTrue(operations)
                self.assertIsNone(cache.active_operation)
                self.assertIs(cache.last_metrics, operations[-1].metrics)
                old.close()

    def test_exclusion_repair_failure_does_not_leave_operation_attached(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / 'files'
            root.mkdir()
            with DirectoryCache(database=base / 'cache' / 'index.sqlite3') as cache:
                with cache.get(root):
                    pass
                with patch('commonUtils.filesystem.index.store.scan_exclusions', return_value=(root / 'excluded',)), patch.object(
                        cache, '_repair_exclusions', side_effect=OperationCancelled('repair cancelled')):
                    with self.assertRaises(OperationCancelled):
                        cache.repair_cached_exclusions(root)
                self.assertIsNone(cache.active_operation)
                with cache.get(root) as snapshot:
                    self.assertTrue(snapshot.complete)
