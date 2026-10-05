"""Run from the parent directory: python3 -m unittest discover -s commonUtils/tests."""

import errno
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils import fileUtils


class FileMoveTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / 'source.txt'
        self.dest = self.root / 'destination.txt'
        self.src.write_text('new')
        self.dest.write_text('old')
        logger = patch.object(fileUtils, 'log')
        logger.start()
        self.addCleanup(logger.stop)

    def test_missing_source_preserves_destination(self):
        self.src.unlink()
        self.assertFalse(fileUtils.move_file(self.src, self.dest))
        self.assertEqual(self.dest.read_text(), 'old')

    def test_same_file_is_noop(self):
        self.assertTrue(fileUtils.move_file(self.src, self.src))
        self.assertEqual(self.src.read_text(), 'new')

    def test_replaces_existing_destination(self):
        self.assertTrue(fileUtils.move_file(self.src, self.dest))
        self.assertEqual(self.dest.read_text(), 'new')
        self.assertFalse(self.src.exists())

    def test_failed_replace_preserves_both_files(self):
        with patch.object(fileUtils.os, 'replace', side_effect=PermissionError('denied')):
            self.assertFalse(fileUtils.move_file(self.src, self.dest))
        self.assertEqual(self.src.read_text(), 'new')
        self.assertEqual(self.dest.read_text(), 'old')

    def test_cross_filesystem_copy_failure_preserves_destination(self):
        def partial_copy(source, target, **kwargs):
            target.write_text('partial')
            raise OSError('copy failed')

        with patch.object(fileUtils.os, 'replace', side_effect=OSError(errno.EXDEV, 'cross-device')), patch.object(
            fileUtils, 'copy2', side_effect=partial_copy
        ):
            self.assertFalse(fileUtils.move_file(self.src, self.dest))
        self.assertEqual(self.src.read_text(), 'new')
        self.assertEqual(self.dest.read_text(), 'old')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['destination.txt', 'source.txt'])

    def test_cross_filesystem_move_stages_then_replaces(self):
        real_replace = fileUtils.os.replace

        def replace(source, target):
            if Path(source) == self.src:
                raise OSError(errno.EXDEV, 'cross-device')
            self.assertEqual(self.dest.read_text(), 'old')
            return real_replace(source, target)

        with patch.object(fileUtils.os, 'replace', side_effect=replace):
            self.assertTrue(fileUtils.move_file(self.src, self.dest))
        self.assertEqual(self.dest.read_text(), 'new')
        self.assertFalse(self.src.exists())
        self.assertEqual(list(self.root.iterdir()), [self.dest])

    def test_cross_filesystem_final_replace_failure_preserves_both_files(self):
        with patch.object(fileUtils.os, 'replace', side_effect=[
            OSError(errno.EXDEV, 'cross-device'), PermissionError('denied')
        ]):
            self.assertFalse(fileUtils.move_file(self.src, self.dest))
        self.assertEqual(self.src.read_text(), 'new')
        self.assertEqual(self.dest.read_text(), 'old')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['destination.txt', 'source.txt'])

    def test_new_destination_parent_is_created(self):
        destination = self.root / 'nested' / 'destination.txt'
        self.assertTrue(fileUtils.move_file(self.src, destination))
        self.assertEqual(destination.read_text(), 'new')
        self.assertFalse(self.src.exists())


if __name__ == '__main__':
    unittest.main()
