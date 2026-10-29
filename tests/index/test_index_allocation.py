"""Both size measures persist, migrate, and update without reading contents."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from unittest.mock import Mock

from commonUtils.filesystem.index import DirectoryCache
from commonUtils.filesystem.index.allocation import allocated_size
from commonUtils.filesystem.index.allocation import _windows_allocation
from commonUtils.filesystem.index.reconcile import reconcile_existing


class AllocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'files'
        self.root.mkdir()
        (self.root / 'nested').mkdir()
        self.small = self.root / 'small'
        self.sparse = self.root / 'nested' / 'sparse'
        self.small.write_bytes(b'x')
        self.sparse.write_bytes(b'x' * 10000)
        self.cache = DirectoryCache(database=self.base / 'cache' / 'index.sqlite3')
        self.addCleanup(self.cache.close)
        self.allocations = {self.small: 4096, self.sparse: 512}
        for module in ('store', 'metadata'):
            patcher = patch(f'commonUtils.filesystem.index.{module}.allocated_size',
                            side_effect=lambda path, info: self.allocations.get(Path(path), 0))
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_both_measures_persist_and_sort_independently_without_scan(self):
        snapshot = self.cache.get(self.root)
        stats = snapshot.folder_stats()[self.root]
        self.assertEqual((stats.size, stats.disk_size, stats.disk_unknown), (10001, 4608, 0))
        self.assertEqual(snapshot.entry(self.small).disk_size, 4096)
        self.assertEqual(snapshot.storage_children(self.root, 10)[0][0], self.root / 'nested')
        self.assertEqual(snapshot.storage_children(self.root, 10, metric='disk_size')[0], (self.small, False, 4096))
        with DirectoryCache(database=self.cache.database) as restarted, \
                patch('os.scandir', side_effect=AssertionError('Cached measures must not scan')):
            saved = restarted.peek(self.root)
            self.assertEqual(saved.folder_stats()[self.root].disk_size, 4608)
            self.assertEqual(saved.storage_children(self.root, 10, metric='disk_size')[1][2], 512)

    def test_allocation_only_change_reconciles_totals_and_keeps_old_reader(self):
        original = self.cache.get(self.root)
        self.allocations[self.small] = 8192
        fresh = reconcile_existing(self.cache, self.root, (), lambda: False, lambda *args: None)
        self.assertEqual(fresh.folder_stats()[self.root].disk_size, 8704)
        self.assertEqual(original.folder_stats()[self.root].disk_size, 4608)
        self.assertEqual(original.entry(self.small).disk_size, 4096)

    def test_unknown_is_counted_and_never_replaced_with_logical_size(self):
        self.allocations[self.sparse] = -1
        stats = self.cache.get(self.root).folder_stats()[self.root]
        self.assertEqual((stats.size, stats.disk_size, stats.disk_unknown), (10001, 4096, 1))

    def test_v3_upgrade_retains_logical_sizes_and_fills_allocation_on_validation(self):
        self.cache.get(self.root).close()
        with closing(sqlite3.connect(self.cache.database)) as db, db:
            db.execute('DROP VIEW indexed_entries')
            db.execute('DROP TABLE entry_allocations')
            db.execute('ALTER TABLE folder_totals DROP COLUMN disk_size')
            db.execute('ALTER TABLE folder_totals DROP COLUMN disk_unknown')
            for identity, in db.execute('SELECT DISTINCT identity FROM entry_records').fetchall():
                old = json.dumps(json.loads(identity)[:6])
                db.execute('UPDATE entry_records SET identity=? WHERE identity=?', (old, identity))
            from commonUtils.filesystem.index.schema import ensure_reader_view
            ensure_reader_view(db)
            db.execute('PRAGMA user_version=3')
        with DirectoryCache(database=self.cache.database) as restarted:
            old = restarted.peek(self.root)
            self.assertEqual(old.folder_stats()[self.root].size, 10001)
            self.assertEqual(old.folder_stats()[self.root].disk_unknown, 2)
            fresh = restarted.get(self.root)
            self.assertEqual(fresh.folder_stats()[self.root].disk_size, 4608)
            self.assertEqual(old.folder_stats()[self.root].size, 10001)
        self.assertTrue(self.cache.database.with_suffix('.pre-v4.sqlite3').exists())

    def test_real_sparse_file_uses_allocated_blocks(self):
        path = self.root / 'real-sparse'
        with path.open('wb') as stream:
            stream.seek(16 * 1024 * 1024)
            stream.write(b'x')
        info = path.stat()
        if not hasattr(info, 'st_blocks'):
            self.skipTest('POSIX allocated blocks unavailable')
        self.assertEqual(allocated_size(path, info), info.st_blocks * 512)
        self.assertLess(allocated_size(path, info), info.st_size)

    def test_missing_platform_allocation_is_unknown(self):
        with patch('commonUtils.filesystem.index.allocation.os.name', 'posix'):
            self.assertEqual(allocated_size('fixture', SimpleNamespace(st_size=123)), -1)

    def test_windows_standard_allocation_reads_metadata_and_closes_handle(self):
        kernel = Mock()
        kernel.CreateFileW.return_value = 0x1234567880000000

        def information(handle, kind, pointer, length):
            pointer._obj.allocation = 8192
            return True

        kernel.GetFileInformationByHandleEx.side_effect = information
        with patch('commonUtils.filesystem.index.allocation._windows_api', return_value=kernel):
            self.assertEqual(_windows_allocation('fixture', SimpleNamespace(st_file_attributes=0)), 8192)
        args = kernel.CreateFileW.call_args.args
        self.assertEqual((args[1], args[2], args[4], args[5]), (0x80, 7, 3, 0x200000))
        kernel.CloseHandle.assert_called_once_with(0x1234567880000000)
        kernel.GetCompressedFileSizeW.assert_not_called()

    def test_windows_failed_allocation_is_unknown_and_closes_valid_handle(self):
        import ctypes
        kernel = Mock()
        kernel.CreateFileW.return_value = ctypes.c_void_p(-1).value
        with patch('commonUtils.filesystem.index.allocation._windows_api', return_value=kernel):
            self.assertEqual(_windows_allocation('fixture', SimpleNamespace(st_file_attributes=0)), -1)
            kernel.CloseHandle.assert_not_called()
            kernel.CreateFileW.return_value = 123
            kernel.GetFileInformationByHandleEx.return_value = False
            self.assertEqual(_windows_allocation('fixture', SimpleNamespace(st_file_attributes=0)), -1)
        kernel.CloseHandle.assert_called_once_with(123)

    def test_windows_sparse_allocation_preserves_large_sizes_and_reports_failure(self):
        kernel = Mock()

        def compressed(path, high):
            high._obj.value = 2
            return 512

        kernel.GetCompressedFileSizeW.side_effect = compressed
        with patch('commonUtils.filesystem.index.allocation._windows_api', return_value=kernel), \
                patch('ctypes.set_last_error', create=True), patch('ctypes.get_last_error', create=True, return_value=5):
            self.assertEqual(_windows_allocation('fixture', SimpleNamespace(st_file_attributes=0x200)), (2 << 32) + 512)
            kernel.GetCompressedFileSizeW.side_effect = None
            kernel.GetCompressedFileSizeW.return_value = 0xffffffff
            self.assertEqual(_windows_allocation('fixture', SimpleNamespace(st_file_attributes=0x800)), -1)
        kernel.CreateFileW.assert_not_called()
