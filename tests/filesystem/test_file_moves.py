"""Run from the parent directory: python3 -m unittest discover -s commonUtils/tests."""

import errno
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.filesystem import files as fileUtils


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
        with self.assertRaises(OSError):
            fileUtils.File(self.src).move_file(self.dest)
        self.assertEqual(self.dest.read_text(), 'old')

    def test_same_file_is_noop(self):
        self.assertEqual(fileUtils.File(self.src).move_file(self.src).path, self.src)
        self.assertEqual(self.src.read_text(), 'new')

    def test_replaces_existing_destination(self):
        self.assertEqual(fileUtils.File(self.src).move_file(self.dest).path, self.dest)
        self.assertEqual(self.dest.read_text(), 'new')
        self.assertFalse(self.src.exists())

    def test_failed_replace_preserves_both_files(self):
        with patch.object(fileUtils.os, 'replace', side_effect=PermissionError('denied')):
            with self.assertRaises(OSError):
                fileUtils.File(self.src).move_file(self.dest)
        self.assertEqual(self.src.read_text(), 'new')
        self.assertEqual(self.dest.read_text(), 'old')

    def test_cross_filesystem_copy_failure_preserves_destination(self):
        def partial_copy(source, target, **kwargs):
            target.write_text('partial')
            raise OSError('copy failed')

        with patch.object(fileUtils.os, 'replace', side_effect=OSError(errno.EXDEV, 'cross-device')), patch.object(
            fileUtils, 'copy2', side_effect=partial_copy
        ):
            with self.assertRaises(OSError):
                fileUtils.File(self.src).move_file(self.dest)
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
            self.assertEqual(fileUtils.File(self.src).move_file(self.dest).path, self.dest)
        self.assertEqual(self.dest.read_text(), 'new')
        self.assertFalse(self.src.exists())
        self.assertEqual(list(self.root.iterdir()), [self.dest])

    def test_cross_filesystem_final_replace_failure_preserves_both_files(self):
        with patch.object(fileUtils.os, 'replace', side_effect=[
            OSError(errno.EXDEV, 'cross-device'), PermissionError('denied')
        ]):
            with self.assertRaises(OSError):
                fileUtils.File(self.src).move_file(self.dest)
        self.assertEqual(self.src.read_text(), 'new')
        self.assertEqual(self.dest.read_text(), 'old')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['destination.txt', 'source.txt'])

    def test_corrupt_cross_volume_copy_preserves_source_and_existing_destination(self):
        original_replace = fileUtils.os.replace
        def rename(source, target):
            if Path(source) == self.src:
                raise OSError(errno.EXDEV, 'different device')
            return original_replace(source, target)
        def corrupt(source, target, **kwargs):
            target.write_bytes(b'corrupt copy')
        with patch.object(fileUtils.os, 'replace', side_effect=rename), patch.object(fileUtils, 'copy2', side_effect=corrupt):
            with self.assertRaises(OSError):
                fileUtils.File(self.src).move_file(self.dest)
        self.assertEqual(self.src.read_text(), 'new')
        self.assertEqual(self.dest.read_text(), 'old')

    def test_changed_cross_volume_source_is_not_published_or_deleted(self):
        original_replace, original_copy = fileUtils.os.replace, fileUtils.copy2
        def rename(source, target):
            if Path(source) == self.src:
                raise OSError(errno.EXDEV, 'different device')
            return original_replace(source, target)
        def copy(source, target, **kwargs):
            original_copy(source, target, **kwargs)
            self.src.write_text('newer source edit')
        with patch.object(fileUtils.os, 'replace', side_effect=rename), patch.object(fileUtils, 'copy2', side_effect=copy):
            with self.assertRaises(OSError):
                fileUtils.File(self.src).move_file(self.dest)
        self.assertEqual(self.src.read_text(), 'newer source edit')
        self.assertEqual(self.dest.read_text(), 'old')

    def test_source_edit_after_publication_preserves_both_and_reports_published_state(self):
        from commonUtils.runtime.operations import MutationIncomplete
        original_replace = fileUtils.os.replace
        def rename(source, target):
            if Path(source) == self.src:
                raise OSError(errno.EXDEV, 'different device')
            original_replace(source, target)
            self.src.write_text('new edit after publication')
        with patch.object(fileUtils.os, 'replace', side_effect=rename):
            with self.assertRaises(MutationIncomplete) as caught:
                fileUtils.File(self.src).move_file(self.dest)
        self.assertTrue(caught.exception.result.destination_published)
        self.assertEqual(caught.exception.result.source_state, 'unknown')
        self.assertEqual(self.src.read_text(), 'new edit after publication')
        self.assertEqual(self.dest.read_text(), 'new')

    def test_new_destination_parent_is_created(self):
        destination = self.root / 'nested' / 'destination.txt'
        self.assertEqual(fileUtils.File(self.src).move_file(destination).path, destination)
        self.assertEqual(destination.read_text(), 'new')
        self.assertFalse(self.src.exists())


if __name__ == '__main__':
    unittest.main()
