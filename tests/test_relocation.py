"""Relocation verifies copied content and rebases links without a consumer."""
import errno
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.filesystem import relocation


class RelocationTests(unittest.TestCase):
    def test_windows_extended_link_paths_compare_in_the_same_namespace(self):
        from pathlib import PureWindowsPath
        for value, expected in ((r'\\?\C:\folder\copy', r'C:\folder\copy'),
                                (r'\\?\UNC\server\share\copy', r'\\server\share\copy')):
            self.assertEqual(relocation.without_extended_prefix(value), expected)
        self.assertTrue(PureWindowsPath(relocation.without_extended_prefix(r'\\?\C:\folder\copy'))
                        .is_relative_to(PureWindowsPath(r'C:\folder')))

    def test_conflicting_destination_preserves_both_locations(self):
        with TemporaryDirectory() as directory:
            old, new = Path(directory) / 'old', Path(directory) / 'new'
            old.mkdir(); new.mkdir()
            old.joinpath('file').write_bytes(b'old')
            new.joinpath('file').write_bytes(b'new')
            with self.assertRaisesRegex(ValueError, 'Both storage locations exist'):
                relocation.relocate_directory(old, new)
            self.assertEqual(old.joinpath('file').read_bytes(), b'old')
            self.assertEqual(new.joinpath('file').read_bytes(), b'new')

    def test_cross_device_copy_verifies_before_removing_source_and_rebases_links(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old, new, outside = root / 'old', root / 'new', root / 'outside'
            old.mkdir(); outside.mkdir()
            old.joinpath('file').write_bytes(b'ciphertext')
            old.joinpath('relocated-copy').symlink_to('../outside', target_is_directory=True)
            relocation.relocate_directory(old, new)
            self.assertFalse(old.exists())
            self.assertEqual(new.joinpath('relocated-copy').resolve(), outside.resolve())
            self.assertEqual(new.joinpath('file').read_bytes(), b'ciphertext')
            old.mkdir()
            old.joinpath('other').write_bytes(b'other ciphertext')
            real_rename = relocation.rename_exclusive
            def different_device(source, destination):
                if Path(source) == old:
                    raise OSError(errno.EXDEV, 'Synthetic cross-device rename')
                return real_rename(source, destination)
            with patch.object(relocation, 'rename_exclusive', side_effect=different_device):
                relocation.relocate_directory(old, root / 'another-volume')
            self.assertEqual(root.joinpath('another-volume/other').read_bytes(), b'other ciphertext')
            self.assertFalse(old.exists())

    def test_failed_copy_keeps_original_and_does_not_publish_destination(self):
        with TemporaryDirectory() as directory:
            old, new = Path(directory) / 'old', Path(directory) / 'new'
            old.mkdir()
            old.joinpath('file').write_bytes(b'original ciphertext')
            with patch.object(relocation, 'rename_exclusive', side_effect=OSError(errno.EXDEV, 'Cross device')), \
                 patch.object(relocation.shutil, 'copytree', side_effect=OSError('Synthetic copy failure')):
                with self.assertRaisesRegex(OSError, 'copy failure'):
                    relocation.relocate_directory(old, new)
            self.assertEqual(old.joinpath('file').read_bytes(), b'original ciphertext')
            self.assertFalse(new.exists())
            self.assertEqual(sorted(path.name for path in old.parent.iterdir()), ['old'])

    def test_relocated_root_and_internal_links_keep_their_targets(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / 'outside'
            outside.mkdir()
            old, new = root / 'old', root / 'new'
            old.symlink_to('outside', target_is_directory=True)
            relocation.relocate_directory(old, new)
            self.assertTrue(new.is_symlink())
            self.assertEqual(new.resolve(), outside.resolve())
            self.assertFalse(old.exists())
            old.mkdir()
            old.joinpath('ciphertext').mkdir()
            old.joinpath('ciphertext/file').write_bytes(b'ciphertext')
            old.joinpath('copy').symlink_to(old / 'ciphertext', target_is_directory=True)
            destination = root / 'moved'
            relocation.relocate_directory(old, destination)
            self.assertEqual(destination.joinpath('copy/file').read_bytes(), b'ciphertext')
            self.assertEqual(destination.joinpath('copy').resolve(), destination.joinpath('ciphertext').resolve())

    def test_changed_source_during_copy_is_preserved_and_not_published(self):
        with TemporaryDirectory() as directory:
            old, new = Path(directory) / 'old', Path(directory) / 'new'
            old.mkdir()
            old.joinpath('file').write_bytes(b'original')
            actual_copy = relocation.shutil.copytree
            def changing_copy(source, destination, **options):
                result = actual_copy(source, destination, **options)
                old.joinpath('file').write_bytes(b'externally changed')
                return result
            with patch.object(relocation, 'rename_exclusive', side_effect=OSError(errno.EXDEV, 'Cross device')), \
                 patch.object(relocation.shutil, 'copytree', side_effect=changing_copy):
                with self.assertRaisesRegex(ValueError, 'changed during relocation'):
                    relocation.relocate_directory(old, new)
            self.assertEqual(old.joinpath('file').read_bytes(), b'externally changed')
            self.assertFalse(new.exists())

    def test_overlapping_directories_are_rejected_before_creating_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            (source / 'file').write_bytes(b'original')
            with self.assertRaisesRegex(ValueError, 'overlap'):
                relocation.relocate_directory(source, source / 'nested' / 'destination')
            self.assertEqual(list(source.iterdir()), [source / 'file'])
