"""Verify ZIP members remain within the selected extraction directory."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

import pyzipper

from commonUtils.archives import legacy as zipUtils


class ZipPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dest = self.root / 'output'
        self.archive = self.root / 'archive.zip'
        logger = patch('commonUtils.archives.legacy.compatibility.log')
        logger.start()
        self.addCleanup(logger.stop)

    def make_archive(self, entries, password=None):
        if password is None:
            with zipfile.ZipFile(self.archive, 'w') as archive:
                for name, content in entries:
                    archive.writestr(name, content)
        else:
            with pyzipper.AESZipFile(self.archive, 'w', encryption=pyzipper.WZ_AES) as archive:
                archive.setpassword(password.encode())
                for name, content in entries:
                    archive.writestr(name, content)

    def test_non_zip_extension_publication_failure_is_reported(self):
        source = self.root / 'pages'
        source.mkdir()
        (source / '01.txt').write_text('page')
        destination = self.root / 'comic.cbz'
        destination.write_bytes(b'original archive')
        with patch('commonUtils.archives.zip_access.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                zipUtils.zip_file(source, destination, keep_root=False)
        self.assertEqual(destination.read_bytes(), b'original archive')
        self.assertFalse(destination.with_suffix('.zip').exists())
        self.assertFalse(list(self.root.glob('.commonutils-zip-*')))
        self.assertEqual((source / '01.txt').read_text(), 'page')

    def test_parent_directory_entries_are_rejected(self):
        self.make_archive([('../outside/', '')])
        self.assertFalse(zipUtils.unzip_file(self.archive, self.dest))
        self.assertFalse((self.root / 'outside').exists())

    def test_parent_file_entries_are_rejected_without_overwriting(self):
        outside = self.root / 'outside.txt'
        outside.write_text('original')
        self.make_archive([('../outside.txt', 'replacement')])
        self.assertFalse(zipUtils.unzip_file(self.archive, self.dest))
        self.assertEqual(outside.read_text(), 'original')

    def test_absolute_directory_entries_are_rejected(self):
        outside = self.root / 'absolute'
        self.make_archive([(outside.as_posix() + '/', '')])
        self.assertFalse(zipUtils.unzip_file(self.archive, self.dest))
        self.assertFalse(outside.exists())

    def test_sibling_with_same_prefix_is_rejected(self):
        self.make_archive([('../output-other/', '')])
        self.assertFalse(zipUtils.unzip_file(self.archive, self.dest))
        self.assertFalse((self.root / 'output-other').exists())

    def test_existing_directory_symlink_cannot_escape_destination(self):
        outside = self.root / 'outside'
        outside.mkdir()
        self.dest.mkdir()
        try:
            (self.dest / 'link').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Directory symlinks unavailable')
        self.make_archive([('link/created/', '')])
        self.assertFalse(zipUtils.unzip_file(self.archive, self.dest))
        self.assertFalse((outside / 'created').exists())

    def test_normal_directories_and_files_extract(self):
        self.make_archive([('empty/', ''), ('nested/', ''), ('nested/file.txt', 'contents')])
        self.assertTrue(zipUtils.unzip_file(self.archive, self.dest))
        self.assertTrue((self.dest / 'empty').is_dir())
        self.assertEqual((self.dest / 'nested' / 'file.txt').read_text(), 'contents')

    def test_encrypted_archives_also_reject_escaping_directories(self):
        self.make_archive([('../outside/', '')], password='test-password')
        self.assertFalse(zipUtils.unzip_file(self.archive, self.dest, pwd='test-password'))
        self.assertFalse((self.root / 'outside').exists())

    def test_normal_encrypted_archive_extracts(self):
        self.make_archive([('nested/file.txt', 'contents')], password='test-password')
        self.assertTrue(zipUtils.unzip_file(self.archive, self.dest, pwd='test-password'))
        self.assertEqual((self.dest / 'nested' / 'file.txt').read_text(), 'contents')


if __name__ == '__main__':
    unittest.main()
