from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.directory_index import scan_metadata
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
            self.assertEqual(len(scan_metadata(root, False).entries), 3)
            with self.assertRaises(OperationCancelled):
                scan_metadata(root, cancelled=lambda: True)
