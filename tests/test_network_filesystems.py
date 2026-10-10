"""Classify shares from mount metadata and keep network traversal out of indexes."""
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from commonUtils import network_filesystems as network
from commonUtils.directory.exclusions import scan_exclusions, is_excluded


class NetworkFilesystemTests(unittest.TestCase):
    def test_unc_and_mapped_windows_drives(self):
        with patch.object(network.sys, 'platform', 'win32'), patch.object(network, '_drive_type') as drive:
            self.assertTrue(network.is_network_location(r'\\server\share\folder'))
            drive.assert_not_called()
            drive.return_value = 4
            self.assertTrue(network.is_network_location(r'Z:\folder'))
            drive.assert_called_with('Z:\\')
            drive.return_value = 3
            self.assertFalse(network.is_network_location(r'C:\folder'))

    def test_linux_mount_table_escaped_spaces_and_network_filesystem_types(self):
        table = ('1 0 1:1 / / rw - ext4 /dev/local rw\n'
                 '2 1 1:2 / /mnt/share\\040name rw - cifs //server/share rw\n'
                 '3 1 1:3 / /mnt/ssh rw - fuse.sshfs host:/ rw\n')
        with patch.object(network.sys, 'platform', 'linux'), patch.object(Path, 'read_text', return_value=table):
            self.assertEqual(network._mounted_network_roots(), (Path('/mnt/share name'), Path('/mnt/ssh')))

    def test_macos_mount_table(self):
        result = SimpleNamespace(stdout='/dev/disk on / (apfs, local)\n//server/share on /Volumes/Share (smbfs, nodev)\n')
        with patch.object(network.sys, 'platform', 'darwin'), patch.object(network.subprocess, 'run', return_value=result):
            self.assertEqual(network._mounted_network_roots(), (Path('/Volumes/Share'),))

    def test_network_mounts_and_descendants_are_excluded_from_local_scans(self):
        root = Path('/').absolute()
        remote = root / 'Volumes/Share'
        local = root / 'Volumes/Local'
        with patch('commonUtils.directory.exclusions.network_mount_roots', return_value=(remote,)):
            excluded = scan_exclusions(root, root / 'private/tmp/index/cache.sqlite')
        self.assertTrue(is_excluded(remote / 'deep/folder', excluded))
        self.assertFalse(is_excluded(local, excluded))
        with patch.object(network.sys, 'platform', 'darwin'), \
                patch.object(network, 'network_mount_roots', return_value=(remote,)):
            self.assertTrue(network.is_network_location(remote / 'folder'))
            self.assertFalse(network.is_network_location(local))

    def test_new_mount_repairs_saved_sizes_without_enumerating_share(self):
        from commonUtils.directory import DirectoryCache, storage_totals
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / 'files'; root.mkdir()
            (root / 'local').write_bytes(b'123')
            remote = root / 'share'; remote.mkdir()
            (remote / 'cached').write_bytes(b'1234567')
            with DirectoryCache(database=base / 'cache' / 'index.sqlite') as cache:
                with patch('commonUtils.directory.exclusions.network_mount_roots', return_value=()):
                    original = cache.get(root)
                    self.assertEqual(storage_totals(original)[root], 10)
                    cache.repair_cached_exclusions(root)
                with patch('commonUtils.directory.exclusions.network_mount_roots', return_value=(remote,)), \
                     patch('commonUtils.directory.store.os.scandir', side_effect=AssertionError('Share enumeration')):
                    cache.repair_cached_exclusions(root)
                    self.assertEqual(storage_totals(cache.peek(root))[root], 3)
                    self.assertEqual(storage_totals(original)[root], 10)
