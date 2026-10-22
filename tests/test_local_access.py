"""Raw filesystem surfaces must respect host-owned provider boundaries."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.filesystem.local_access import protect_local_root, check_local_path, provider_record_access
from commonUtils.persistence import atomic_write_bytes
from commonUtils.runtime.resources.local import LocalFiles


class LocalAccessTests(unittest.TestCase):
    def test_raw_saves_transfers_deletion_and_rename_are_blocked(self):
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
                alias = outside / 'alias'
                alias.symlink_to(protected, target_is_directory=True)
                with self.assertRaises(PermissionError): atomic_write_bytes(alias / 'new', b'plaintext')
                self.assertEqual(original.read_bytes(), b'opaque')
                self.assertEqual([p.name for p in protected.iterdir()], ['document'])
                atomic_write_bytes(outside / 'ordinary', b'local')
            finally:
                release()

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
