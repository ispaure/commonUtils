"""Writer operations isolate transient state while retaining durable snapshots."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.filesystem.index import DirectoryCache
from commonUtils.runtime.operations import OperationCancelled


class IndexOperationStateTests(unittest.TestCase):
    def test_reconciliation_metadata_uses_its_captured_writer_context(self):
        import json
        import sqlite3
        from types import SimpleNamespace
        from commonUtils.filesystem.index.operation import IndexWriterContext, ScanState
        from commonUtils.filesystem.index.metadata import entry_fingerprint
        from commonUtils.filesystem.index.reconcile import _changed
        with TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / 'one.txt'
            file.write_bytes(b'first')
            with sqlite3.connect(':memory:') as db:
                db.execute('CREATE TABLE folders(generation,path,identity,status)')
                db.execute('CREATE TABLE entries(generation,parent,path,identity)')
                db.execute('INSERT INTO folders VALUES(1,?,?,?)', (str(root), 'same', 'done'))
                db.execute('INSERT INTO entries VALUES(1,?,?,?)',
                           (str(root), str(file), json.dumps(entry_fingerprint(file, file.lstat()))))
                context = IndexWriterContext(db, 1, ScanState())
                # No mutable active-operation lookup exists on this collaborator.
                cache = SimpleNamespace(_folder_identity=lambda *_: 'same')
                self.assertFalse(_changed(context, cache, root, root, lambda: False, lambda *_: None))
                self.assertEqual(context.state.checked_entries, 1)
                file.write_bytes(b'different')
                self.assertTrue(_changed(context, cache, root, root, lambda: False, lambda *_: None))

    def test_scan_validation_uses_explicit_context_and_marks_only_its_totals(self):
        import sqlite3
        from commonUtils.filesystem.index.operation import IndexWriterContext, ScanState
        from commonUtils.filesystem.index.validation import validate
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with sqlite3.connect(':memory:') as db:
                db.execute('CREATE TABLE errors(generation,path,error)')
                db.execute('CREATE TABLE folders(generation,path,identity,status)')
                db.execute('INSERT INTO folders VALUES(1,?,?,?)', (str(root), 'old', 'done'))
                state = ScanState()
                context = IndexWriterContext(db, 1, state)
                self.assertFalse(validate(context, root, lambda: False, lambda *_: None,
                                          folder_identity=lambda *_: 'changed', check_files=False))
                self.assertEqual(state.dirty_totals, {root})
                self.assertEqual(db.execute('SELECT status FROM folders').fetchone()[0], 'pending')
                self.assertFalse(ScanState().dirty_totals)

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
