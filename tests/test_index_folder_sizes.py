"""Index aggregates, cached reads and incomplete recursive size semantics."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch
from commonUtils.directory_index import DirectoryCache, storage_totals
from commonUtils.operations import OperationCancelled
from commonUtils.filesystem import scan_folders


class IndexedSizeTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'files';self.root.mkdir()
        (self.root/'sub').mkdir();(self.root/'sub'/'nested').mkdir()
        (self.root/'sub'/'nested'/'comic.CBZ').write_bytes(b'1234567')
        (self.root/'plain.txt').write_bytes(b'123')
        self.cache=DirectoryCache(database=self.base/'cache'/'index.sqlite3')
        self.addCleanup(self.cache.close)

    def test_aggregates_persist_and_are_shared_by_compatibility_api_and_storage(self):
        snapshot=self.cache.get(self.root)
        stats=snapshot.folder_stats()
        self.assertEqual((stats[self.root].size,stats[self.root].files,stats[self.root].folders),(10,2,2))
        self.assertEqual(stats[self.root].extension_counts,{'cbz':1,'txt':1})
        self.assertTrue(stats[self.root].complete)
        self.assertEqual(storage_totals(snapshot)[self.root],10)
        with patch('commonUtils.directory_index.directory_cache',self.cache):
            self.assertEqual(scan_folders(self.root)[self.root].size,10)
        with DirectoryCache(database=self.cache.database) as restarted:
            with patch('commonUtils.directory_index.os.scandir',side_effect=AssertionError('Cached read scanned')):
                saved=restarted.peek(self.root)
                self.assertEqual(saved.folder_stats([self.root])[self.root].size,10)
                self.assertTrue(saved.folder_stats([self.root])[self.root].stale)

    def test_nested_in_place_writes_are_validated_without_parent_mtime_assumption(self):
        first=self.cache.get(self.root);stamp=self.root.stat().st_mtime_ns
        (self.root/'sub'/'nested'/'comic.CBZ').write_bytes(b'x'*30)
        self.assertEqual(self.root.stat().st_mtime_ns,stamp)
        fresh=self.cache.get(self.root)
        self.assertEqual(fresh.folder_stats()[self.root].size,33)
        self.assertEqual(first.folder_stats()[self.root].size,10)

    def test_browser_totals_read_one_level_and_keep_recursive_sizes(self):
        snapshot = self.cache.get(self.root)
        statements = []
        snapshot.entries.connection.set_trace_callback(statements.append)
        stats = snapshot.folder_stats(children_of=self.root)
        self.assertEqual(set(stats), {self.root, self.root / 'sub'})
        self.assertEqual(stats[self.root / 'sub'].size, 7)
        self.assertEqual(stats[self.root].size, 10)
        self.assertTrue(any('parent_id=' in sql for sql in statements))
        with patch('commonUtils.directory_index.directory_cache', self.cache):
            self.assertEqual(set(scan_folders(self.root, visible_only=True)), set(stats))
            self.assertIn(self.root / 'sub' / 'nested', scan_folders(self.root))
        scoped = self.cache.peek(self.root / 'sub')
        self.assertEqual(set(scoped.folder_stats(children_of=scoped.root)),
                         {self.root / 'sub', self.root / 'sub' / 'nested'})

    def test_partial_sizes_are_not_marked_final_and_retry_permissions(self):
        import os
        real=os.scandir
        def scan(path):
            if Path(path)==self.root/'sub':raise PermissionError('Offline folder')
            return real(path)
        with patch('commonUtils.directory_index.os.scandir',side_effect=scan):
            partial=self.cache.get(self.root)
        self.assertFalse(partial.complete)
        stats=partial.folder_stats()
        self.assertFalse(stats[self.root].complete)
        self.assertEqual(stats[self.root].size,3)
        self.assertGreater(stats[self.root].skipped,0)
        self.assertEqual(self.cache.get(self.root).folder_stats()[self.root].size,10)

    def test_cancel_and_disconnected_root_keep_saved_sizes_readable(self):
        original=self.cache.get(self.root)
        (self.root/'new.txt').write_text('new')
        cancel=Event()
        def report(done,total,message):
            if message.startswith('Indexing '):cancel.set()
        with self.assertRaises(OperationCancelled):self.cache.get(self.root,cancelled=cancel.is_set,report=report)
        previous=self.cache.peek(self.root,partial=False)
        self.assertEqual(previous.folder_stats()[self.root].size,10)
        moved=self.root.with_name('unmounted');self.root.rename(moved)
        with self.assertRaises(NotADirectoryError):self.cache.get(self.root)
        self.assertEqual(self.cache.peek(self.root,partial=False).folder_stats()[self.root].size,10)

    def test_recent_background_requests_coalesce_and_explicit_invalidation_still_checks(self):
        self.cache.get(self.root, reuse_for=2)
        with patch.object(self.cache, '_validate', side_effect=AssertionError('Duplicate validation')):
            self.assertTrue(self.cache.get(self.root, reuse_for=2).reused)
        (self.root/'plain.txt').write_text('changed content')
        self.cache.invalidate(self.root/'plain.txt')
        self.assertEqual(self.cache.get(self.root, reuse_for=2).folder_stats()[self.root].size,22)
