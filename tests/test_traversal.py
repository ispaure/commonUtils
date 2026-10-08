"""Filtered traversal preserves its depth, link and cancellation contracts."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.operations import OperationCancelled
from commonUtils.traversal import scan_directory


class TraversalTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def file(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
        return path

    def test_scanning_filters_depth_hidden_and_does_not_follow_symlink_directories(self):
        a = self.file('a.txt');self.file('.hidden.txt');self.file('b.JPG')
        child = self.file('Folder/child.txt');self.file('Folder/Deep/deep.txt')
        (self.root / 'Link').symlink_to(child.parent, target_is_directory=True)
        self.assertEqual(scan_directory(self.root, mask='*.TXT'), [a])
        files = scan_directory(self.root, mask='*.txt', recursive=True, max_depth=1)
        self.assertEqual(set(files), {a, child})
        files = scan_directory(self.root, hidden=True, mask=r'.*\.txt$', regex=True)
        self.assertEqual(len(files), 2)
        with self.assertRaises(OperationCancelled):
            scan_directory(self.root, cancelled=lambda: True)


    def test_folder_selection_and_natural_order(self):
        self.file('Folder/page10.txt')
        self.file('Folder/page2.txt')
        self.assertEqual([path.name for path in scan_directory(self.root / 'Folder')],
                         ['page2.txt', 'page10.txt'])
        self.assertEqual(scan_directory(self.root, files=False, folders=True),
                         [self.root / 'Folder'])
