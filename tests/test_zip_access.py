"""Plain/AES content parity, authentication and failure-safe archive operations."""

from pathlib import Path
from tempfile import TemporaryDirectory
import stat
import unittest
from unittest.mock import patch
import zipfile
import pyzipper

from commonUtils import zipUtils, zip_access as access
from commonUtils.fileTypes.zipType import ZIPFile


class ZipAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'nested').mkdir()
        (self.source / 'nested' / 'empty').mkdir()
        (self.source / 'nested' / 'é.txt').write_bytes(b'payload\x00with bytes')
        (self.source / 'small.txt').write_bytes(b'x')
        self.password = 'test-only-%-é'

    def write(self, name, password=None):
        path = self.root / name
        zipUtils.zip_file(self.source, path, keep_root=False, password=password)
        return path

    def test_encrypted_and_plain_archives_have_identical_entries_and_bytes(self):
        plain = self.write('plain.zip')
        encrypted = self.write('encrypted.zip', self.password)
        self.assertEqual(access.archive_manifest(plain), access.archive_manifest(encrypted, password=self.password))
        with pyzipper.AESZipFile(encrypted) as archive:
            self.assertTrue(all(info.flag_bits & 1 for info in archive.infolist() if not info.is_dir()))
            self.assertTrue(all(info.wz_aes_strength == 3 for info in archive.infolist() if not info.is_dir()))
        for path, password, name in [(plain, None, 'plain-out'), (encrypted, self.password, 'encrypted-out')]:
            self.assertTrue(ZIPFile(path).extract(self.root / name, password=password))
            self.assertEqual((self.root / name / 'nested/é.txt').read_bytes(), b'payload\x00with bytes')
            self.assertTrue((self.root / name / 'nested/empty').is_dir())

    def test_password_errors_never_echo_password(self):
        path = self.write('encrypted.zip', self.password)
        for password in [None, '', 'wrong-test-secret']:
            with self.assertRaises(access.ArchivePasswordError) as caught:
                access.authenticate(path, password)
            self.assertNotIn('wrong-test-secret', str(caught.exception))
            self.assertNotIn(self.password, str(caught.exception))

    def test_failed_extract_keeps_existing_file_and_removes_partials(self):
        path = self.write('encrypted.zip', self.password)
        destination = self.root / 'output'
        destination.mkdir()
        (destination / 'small.txt').write_bytes(b'original')
        self.assertFalse(zipUtils.unzip_file(path, destination, pwd='wrong'))
        self.assertEqual((destination / 'small.txt').read_bytes(), b'original')
        self.assertFalse(list(destination.rglob('.part_*')))

    def test_aes_authentication_detects_corrupted_ciphertext(self):
        path = self.write('encrypted.zip', self.password)
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo('small.txt')
        data = bytearray(path.read_bytes())
        start = info.header_offset
        name_size = int.from_bytes(data[start + 26:start + 28], 'little')
        extra_size = int.from_bytes(data[start + 28:start + 30], 'little')
        # AES payload includes 16 salt bytes, 2 verifier bytes, then ciphertext.
        data[start + 30 + name_size + extra_size + 18] ^= 1
        path.write_bytes(data)
        with self.assertRaises((access.ArchivePasswordError, zipfile.BadZipFile)):
            access.archive_manifest(path, password=self.password)

    def test_every_path_is_validated_before_plain_or_encrypted_extraction(self):
        for password in [None, self.password]:
            path = self.root / 'unsafe.zip'
            with access.open_archive(path, 'w', password=password) as archive:
                archive.writestr('good.txt', b'good')
                archive.writestr('../bad.txt', b'bad')
            destination = self.root / 'unsafe-output'
            self.assertFalse(zipUtils.unzip_file(path, destination, pwd=password))
            self.assertFalse((destination / 'good.txt').exists())

    def test_symlink_entries_rejected_for_plain_and_aes(self):
        for password in [None, self.password]:
            path = self.root / 'link.zip'
            with access.open_archive(path, 'w', password=password) as archive:
                cls = pyzipper.zipfile_aes.AESZipInfo if password else zipfile.ZipInfo
                info = cls('link')
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, b'outside')
            self.assertFalse(zipUtils.unzip_file(path, self.root / 'link-out', pwd=password))

    def test_empty_password_is_never_written_unencrypted(self):
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            access.write_directory(self.source, self.root / 'empty.zip', password='')
        self.assertFalse((self.root / 'empty.zip').exists())

    def test_create_selection_deduplicates_roots_and_preserves_sources(self):
        output = self.root / 'selected.zip'
        before = (self.source / 'small.txt').read_bytes()
        access.create_archive([self.source, self.source / 'small.txt'], output, password=self.password)
        manifest = access.archive_manifest(output, password=self.password)
        self.assertIn('source/nested/empty/', manifest)
        self.assertIn('source/small.txt', manifest)
        self.assertEqual((self.source / 'small.txt').read_bytes(), before)
        self.assertEqual(len(manifest), 5)

    def test_output_inside_source_and_existing_output_are_rejected(self):
        with self.assertRaises(ValueError):
            access.create_archive([self.source], self.source / 'new.zip', password=self.password)
        output = self.root / 'existing.zip'
        output.write_bytes(b'original')
        with self.assertRaises(FileExistsError):
            access.create_archive([self.source], output, password=self.password)
        self.assertEqual(output.read_bytes(), b'original')

    def test_colliding_selection_names_are_rejected_before_output(self):
        other = self.root / 'other'
        other.mkdir()
        (other / 'small.txt').write_bytes(b'other')
        output = self.root / 'collision.zip'
        with self.assertRaisesRegex(ValueError, 'colliding'):
            access.create_archive([self.source / 'small.txt', other / 'small.txt'], output, password=self.password)
        self.assertFalse(output.exists())

    def test_creation_verification_failure_publishes_nothing(self):
        output = self.root / 'failed.zip'
        with patch.object(access, 'archive_manifest', return_value={}):
            with self.assertRaisesRegex(ValueError, 'verification'):
                access.create_archive([self.source], output, password=self.password)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob('.logistics-zip-*')))

    def test_member_info_copy_preserves_names_and_permissions_but_not_crypto_headers(self):
        encrypted = self.write('encrypted.zip', self.password)
        copied = self.root / 'copied.zip'
        with access.open_archive(encrypted, password=self.password) as source, access.open_archive(
                copied, 'w', password=self.password) as target:
            for info in source.infolist():
                target.writestr(access.copy_member_info(info, target), source.read(info))
        self.assertEqual(access.archive_manifest(encrypted, password=self.password),
                         access.archive_manifest(copied, password=self.password))

    def test_unicode_equivalent_names_are_rejected_before_extraction(self):
        for password in (None, self.password):
            path = self.root / 'unicode.zip'
            with access.open_archive(path, 'w', password=password) as archive:
                archive.writestr('é.txt', b'first')
                archive.writestr('e\u0301.txt', b'second')
            destination = self.root / 'unicode-output'
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                access.extract_archive(path, destination, password=password)
            self.assertFalse(destination.exists())

    def test_directory_payload_is_rejected_instead_of_silently_discarded(self):
        for password in (None, self.password):
            path = self.root / 'directory-payload.zip'
            with access.open_archive(path, 'w', password=password) as archive:
                archive.writestr('folder/', b'not an empty directory')
            with self.assertRaisesRegex(ValueError, 'directory contains file data'):
                access.archive_manifest(path, password=password)

    def test_output_via_symlink_into_source_is_rejected_before_work(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'outside'):
            access.create_archive([self.source], alias / 'new.zip', password=self.password)
        self.assertFalse(list(self.source.glob('.logistics-zip-*')))
        self.assertFalse((self.source / 'new.zip').exists())

    def test_source_change_during_verification_prevents_publication(self):
        output = self.root / 'changed.zip'
        real_manifest = access.archive_manifest
        def verify(*args, **kwargs):
            result = real_manifest(*args, **kwargs)
            (self.source / 'small.txt').write_bytes(b'externally changed')
            return result
        with patch.object(access, 'archive_manifest', side_effect=verify):
            with self.assertRaisesRegex(RuntimeError, 'Source changed'):
                access.create_archive([self.source], output, password=self.password)
        self.assertFalse(output.exists())
        self.assertEqual((self.source / 'small.txt').read_bytes(), b'externally changed')
        self.assertFalse(list(self.root.glob('.logistics-zip-*')))

    def test_competing_output_is_never_overwritten(self):
        output = self.root / 'competing.zip'
        real_manifest = access.archive_manifest
        def verify(*args, **kwargs):
            result = real_manifest(*args, **kwargs)
            output.write_bytes(b'other operation')
            return result
        with patch.object(access, 'archive_manifest', side_effect=verify):
            with self.assertRaises(FileExistsError):
                access.create_archive([self.source], output, password=self.password)
        self.assertEqual(output.read_bytes(), b'other operation')
        self.assertFalse(list(self.root.glob('.logistics-zip-*')))

    def test_unicode_equivalent_selected_names_are_rejected_before_output(self):
        first_folder, second_folder = self.root / 'first', self.root / 'second'
        first_folder.mkdir()
        second_folder.mkdir()
        first, second = first_folder / 'é.txt', second_folder / 'e\u0301.txt'
        first.write_bytes(b'first')
        second.write_bytes(b'second')
        output = self.root / 'unicode-selected.zip'
        with self.assertRaisesRegex(ValueError, 'colliding'):
            access.create_archive([first, second], output, password=self.password)
        self.assertFalse(output.exists())
        self.assertEqual(first.read_bytes(), b'first')
        self.assertEqual(second.read_bytes(), b'second')

    def test_creation_compression_options_apply_to_plain_and_aes_streams(self):
        source = self.root / 'compressible.txt'
        source.write_bytes((b'abcdefghij' * 10000 + b'klmnopqrst' * 10000) * 5)
        for password in (None, self.password):
            sizes = []
            for level in (1, 9):
                output = self.root / f'level-{bool(password)}-{level}.zip'
                access.create_archive([source], output, password=password, compresslevel=level)
                with access.open_archive(output, password=password) as archive:
                    self.assertEqual(archive.read(source.name), source.read_bytes())
                sizes.append(output.stat().st_size)
            self.assertLess(sizes[1], sizes[0])
            stored = self.root / f'stored-{bool(password)}.zip'
            access.create_archive([source], stored, password=password, compression=zipfile.ZIP_STORED)
            self.assertGreater(stored.stat().st_size, sizes[0])
            with access.open_archive(stored, password=password) as archive:
                self.assertEqual(archive.read(source.name), source.read_bytes())

    def test_authentication_honours_cancellation_during_payload_read(self):
        from commonUtils.operations import OperationCancelled
        path = self.write('cancel-auth.zip', self.password)
        calls = 0
        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 3
        with self.assertRaises(OperationCancelled):
            access.authenticate(path, self.password, all_members=True, cancelled=cancelled)
