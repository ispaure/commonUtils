from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.directory_index import scan_metadata, storage_totals, DirectoryCache
from unittest.mock import patch
from commonUtils.operations import OperationCancelled


class DirectoryIndexTests(unittest.TestCase):
    def test_partial_case_insensitive_search_recursion_sizes_and_links(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'Folder').mkdir()
            (root / 'Folder' / 'BIG.txt').write_bytes(b'12345')
            (root / 'small.txt').write_bytes(b'1')
            (root / 'link').symlink_to(root / 'Folder', target_is_directory=True)
            snapshot = scan_metadata(root)
            self.assertEqual(len(snapshot.search('fol')), 1)
            self.assertEqual(snapshot.search('big')[0].size, 5)
            self.assertEqual(len(snapshot.entries), 4)
            self.assertEqual(storage_totals(snapshot)[snapshot.root], 6)
            self.assertEqual(storage_totals(snapshot)[snapshot.root / 'Folder'], 5)
            self.assertEqual(len(scan_metadata(root, False).entries), 3)
            with self.assertRaises(OperationCancelled):
                scan_metadata(root, cancelled=lambda: True)

    def test_cache_reuses_metadata_and_detects_contents_and_nested_membership_changes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'nested').mkdir()
            file = root / 'nested' / 'file.txt'
            file.write_bytes(b'one')
            cache = DirectoryCache()
            first = cache.get(root)
            with patch('commonUtils.directory_index.os.scandir', side_effect=AssertionError('Repeated enumeration')):
                reused = cache.get(root)
                self.assertTrue(reused.reused)
                self.assertEqual(reused.scanned_at, first.scanned_at)
                self.assertEqual(len(cache.get(root, False).entries), 1)
            file.write_bytes(b'changed')
            self.assertFalse(cache.get(root).reused)
            self.assertEqual(cache.get(root).search('file')[0].size, 7)
            (root / 'nested' / 'new.txt').write_bytes(b'new')
            self.assertFalse(cache.get(root).reused)
            self.assertEqual(len(cache.get(root).entries), 3)
            self.assertFalse(cache.get(root, refresh=True).reused)
            cache.invalidate(file)
            self.assertFalse(cache.get(root).reused)
            file.unlink()
            self.assertFalse(cache.get(root).reused)
