"""Folder totals exclude links and support cancellation."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


class FolderStatsTests(unittest.TestCase):
    def test_recursive_sizes_counts_links_and_cancellation(self):
        from commonUtils.filesystem import scan_folders
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / 'one' / 'two'
            nested.mkdir(parents=True)
            (root / 'a.cbz').write_bytes(b'12345')
            (nested / 'b.CBZ').write_bytes(b'123')
            (nested.parent / 'notes.txt').write_bytes(b'12')
            (nested / 'cycle').symlink_to(root, target_is_directory=True)
            totals = scan_folders(root)
            self.assertEqual(totals[root].size, 10)
            self.assertEqual(totals[root].files, 3)
            self.assertEqual(totals[root].extension_counts['cbz'], 2)
            self.assertEqual(totals[root].folders, 2)
            self.assertEqual(totals[root].skipped, 1)
            self.assertEqual(totals[nested].size, 3)
            self.assertIsNone(scan_folders(root, lambda: True))
