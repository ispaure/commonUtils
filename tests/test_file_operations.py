"""Clipboard transfer semantics preserve originals, links and existing destinations."""

import errno
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils import file_operations as operations


class FileTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'; self.source.mkdir()
        self.destination = self.root / 'destination'; self.destination.mkdir()
        self.file = self.source / 'example.txt'; self.file.write_text('original')

    def test_copy_and_collisions_preserve_original_and_existing_data(self):
        existing = self.destination / self.file.name; existing.write_text('existing')
        result = operations.transfer_paths([self.file], self.destination)
        self.assertFalse(result.failures)
        self.assertEqual(self.file.read_text(), 'original')
        self.assertEqual(existing.read_text(), 'existing')
        self.assertEqual((self.destination / 'example copy.txt').read_text(), 'original')
        operations.transfer_paths([self.file], self.destination)
        self.assertEqual((self.destination / 'example copy 2.txt').read_text(), 'original')

    def test_same_folder_copy_duplicates_and_cut_is_noop(self):
        copied = operations.transfer_paths([self.file], self.source)
        self.assertEqual(copied.completed[0][1], self.source.resolve() / 'example copy.txt')
        moved = operations.transfer_paths([self.file], self.source, move=True)
        self.assertEqual(moved.completed[0][0], moved.completed[0][1])
        self.assertTrue(self.file.exists())

    def test_move_never_overwrites_and_handles_folder_trees(self):
        folder = self.source / 'Tree'; folder.mkdir()
        (folder / 'child').write_text('child')
        (self.destination / 'Tree').mkdir()
        result = operations.transfer_paths([folder, self.file], self.destination, move=True)
        self.assertFalse(result.failures)
        self.assertFalse(folder.exists()); self.assertFalse(self.file.exists())
        self.assertEqual((self.destination / 'Tree copy/child').read_text(), 'child')
        self.assertTrue((self.destination / 'Tree').is_dir())

    def test_parent_and_child_selection_is_copied_once_and_links_are_not_followed(self):
        folder = self.source / 'Tree'; folder.mkdir()
        child = folder / 'child'; child.write_text('child')
        (folder / 'link').symlink_to(self.file)
        result = operations.transfer_paths([child, folder, folder], self.destination)
        self.assertEqual(len(result.completed), 1)
        self.assertTrue((self.destination / 'Tree/link').is_symlink())
        self.assertEqual((self.destination / 'Tree/child').read_text(), 'child')
        self.assertFalse((self.destination / 'child').exists())

    def test_dangling_link_is_copied_and_moved_as_a_link(self):
        link = self.source / 'dangling'; link.symlink_to('missing')
        copied = operations.transfer_paths([link], self.destination)
        self.assertFalse(copied.failures)
        self.assertTrue((self.destination / 'dangling').is_symlink())
        moved = operations.transfer_paths([link], self.destination, move=True)
        self.assertFalse(moved.failures)
        self.assertFalse(link.is_symlink())
        self.assertTrue((self.destination / 'dangling copy').is_symlink())

    def test_cannot_paste_directory_into_itself_or_symlinked_descendant(self):
        child = self.source / 'child'; child.mkdir()
        alias = self.root / 'alias'; alias.symlink_to(child, target_is_directory=True)
        for directory in (self.source, child, alias):
            for move in (False, True):
                result = operations.transfer_paths([self.source], directory, move=move)
                self.assertEqual(len(result.failures), 1)
                self.assertEqual(result.completed, ())
                self.assertTrue(self.file.exists())
                self.assertFalse(list(directory.glob('.file-transfer-*')))

    def test_failed_staged_copy_keeps_sources_and_does_not_publish_partial_items(self):
        def fail(source, destination):
            destination.write_text('partial')
            raise OSError('copy failed')
        with patch.object(operations, '_copy', fail):
            result = operations.transfer_paths([self.file], self.destination)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(list(self.destination.iterdir()), [])
        self.assertEqual(self.file.read_text(), 'original')

    def test_racing_destination_is_not_replaced(self):
        original = operations.rename_path
        def race(source, target):
            target.write_text('racing writer')
            original(source, target)
        with patch.object(operations, 'rename_path', race):
            result = operations.transfer_paths([self.file], self.destination)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual((self.destination / self.file.name).read_text(), 'racing writer')
        self.assertEqual(self.file.read_text(), 'original')
        self.assertFalse(list(self.destination.glob('.file-transfer-*')))

    def test_cross_volume_move_stages_before_removing_source(self):
        original = operations.rename_path
        def rename(source, target):
            if source == self.file.resolve():
                raise OSError(errno.EXDEV, 'different device')
            self.assertTrue(self.file.exists())
            original(source, target)
        with patch.object(operations, 'rename_path', rename):
            result = operations.transfer_paths([self.file], self.destination, move=True)
        self.assertFalse(result.failures)
        self.assertFalse(self.file.exists())
        self.assertEqual((self.destination / self.file.name).read_text(), 'original')

    def test_changed_cross_volume_source_is_kept_and_copy_is_not_published(self):
        original_rename, original_copy = operations.rename_path, operations._copy
        def rename(source, target):
            if source == self.file.resolve():
                raise OSError(errno.EXDEV, 'different device')
            original_rename(source, target)
        def copy(source, target):
            original_copy(source, target)
            self.file.write_text('edited during copy')
        with patch.object(operations, 'rename_path', rename), patch.object(operations, '_copy', copy):
            result = operations.transfer_paths([self.file], self.destination, move=True)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(self.file.read_text(), 'edited during copy')
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_cancel_stops_between_items_and_reports_completed_moves(self):
        second = self.source / 'second'; second.write_text('second')
        def cancelled():
            return not self.file.exists()
        result = operations.transfer_paths([self.file, second], self.destination, move=True, cancelled=cancelled)
        self.assertTrue(result.cancelled)
        self.assertEqual(len(result.completed), 1)
        self.assertTrue(second.exists())
        self.assertEqual((self.destination / self.file.name).read_text(), 'original')

    def test_one_missing_item_does_not_prevent_other_items(self):
        result = operations.transfer_paths([self.source / 'missing', self.file], self.destination)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(len(result.completed), 1)

    def test_filename_validation_rejects_paths_and_preserves_native_unicode(self):
        for name in ('', '.', '..', 'child/name', 'bad\x00name'):
            with self.assertRaises(ValueError): operations.validate_name(name)
        operations.validate_name('日本語 comic.txt')
