"""Raw filesystem surfaces must respect host-owned provider boundaries."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.filesystem.local_access import protect_local_root, check_local_path, provider_record_access
from commonUtils.persistence import atomic_write_bytes
from commonUtils.runtime.resources.local import LocalFiles


class LocalAccessTests(unittest.TestCase):
    def test_raw_saves_transfers_deletion_and_rename_are_blocked(self):
        from commonUtils.formats.csvType import CSVFile
        from commonUtils.filesystem.transfers import transfer_paths
        from commonUtils.filesystem.removal import removal_plan, remove_items
        from commonUtils.filesystem.rename import rename_path, plan_named_renames, apply_renames
        with TemporaryDirectory() as folder:
            root = Path(folder)
            protected, outside = root / 'managed', root / 'outside'
            protected.mkdir(); outside.mkdir()
            original = protected / 'document'
            original.write_bytes(b'opaque')
            release = protect_local_root(self.id(), protected, 'Use the provider')
            try:
                with self.assertRaises(PermissionError): atomic_write_bytes(original, b'plaintext')
                with self.assertRaises(PermissionError): atomic_write_bytes(protected / 'new', b'plaintext')
                with self.assertRaises(PermissionError): rename_path(original, protected / 'renamed')
                self.assertFalse(apply_renames(plan_named_renames([(original, 'renamed')])).success)
                self.assertTrue(transfer_paths([original], outside).failures)
                self.assertTrue(remove_items(removal_plan([protected]), permanent=True).failures)
                with self.assertRaises(PermissionError): check_local_path(root, recursive=True)
                with self.assertRaises(PermissionError): LocalFiles(protected).mkdir('raw')
                with self.assertRaises(PermissionError):
                    CSVFile(protected / 'nested/table.csv').write_csv([['private']])
                alias = outside / 'alias'
                alias.symlink_to(protected, target_is_directory=True)
                with self.assertRaises(PermissionError): atomic_write_bytes(alias / 'new', b'plaintext')
                self.assertEqual(original.read_bytes(), b'opaque')
                self.assertEqual([p.name for p in protected.iterdir()], ['document'])
                atomic_write_bytes(outside / 'ordinary', b'local')
            finally:
                release()

    def test_file_object_mutations_respect_source_and_destination_boundaries(self):
        from commonUtils.filesystem.files import File
        for action in ('copy_out', 'copy_in', 'move_out', 'delete', 'writable', 'rename'):
            with self.subTest(action=action), TemporaryDirectory() as directory:
                root = Path(directory)
                protected = root / 'managed'
                protected.mkdir()
                source, outside = protected / 'document', root / 'ordinary'
                source.write_bytes(b'opaque')
                outside.write_bytes(b'ordinary')
                release = protect_local_root(self.id(), protected, 'Use the provider')
                try:
                    operations = {
                        'copy_out': lambda: File(source).copy_file(root / 'copied'),
                        'copy_in': lambda: File(outside).copy_file(source),
                        'move_out': lambda: File(source).move_file(root / 'moved'),
                        'delete': lambda: File(source).delete_file(),
                        'writable': lambda: File(source).make_writable(),
                        'rename': lambda: File(source).rename_file(root / 'nested/renamed'),
                    }
                    with self.assertRaises(PermissionError):
                        operations[action]()
                    self.assertEqual(source.read_bytes(), b'opaque')
                    self.assertEqual(outside.read_bytes(), b'ordinary')
                    self.assertFalse((root / 'nested').exists())
                finally:
                    release()

    def test_directory_object_deletion_preflights_protected_descendants(self):
        from commonUtils.filesystem.directories import Directory
        for action in ('root', 'contents', 'ancestor_contents'):
            with self.subTest(action=action), TemporaryDirectory() as directory:
                root = Path(directory)
                protected = root / 'managed'
                protected.mkdir()
                source, ordinary = protected / 'document', root / 'ordinary'
                source.write_bytes(b'opaque')
                ordinary.write_bytes(b'keep sibling')
                release = protect_local_root(self.id(), protected, 'Use the provider')
                try:
                    with self.assertRaises(PermissionError):
                        if action == 'root':
                            Directory(protected).delete()
                        elif action == 'contents':
                            Directory(protected).delete_contents()
                        else:
                            Directory(root).delete_contents()
                    self.assertEqual(source.read_bytes(), b'opaque')
                    self.assertEqual(ordinary.read_bytes(), b'keep sibling')
                finally:
                    release()

    def test_unregistered_cyclic_directory_link_can_still_be_deleted(self):
        from commonUtils.filesystem.directories import Directory
        with TemporaryDirectory() as directory:
            loop = Path(directory) / 'loop'
            loop.symlink_to('loop', target_is_directory=True)
            Directory(loop).delete()
            self.assertFalse(loop.is_symlink())

    def test_backend_record_grant_is_exact_and_scoped(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            release = protect_local_root(self.id(), root, 'Use the provider')
            try:
                with provider_record_access(root / 'record'):
                    atomic_write_bytes(root / 'record', b'metadata')
                    with self.assertRaises(PermissionError): atomic_write_bytes(root / 'other', b'wrong')
                with self.assertRaises(PermissionError): atomic_write_bytes(root / 'record', b'wrong')
            finally:
                release()
