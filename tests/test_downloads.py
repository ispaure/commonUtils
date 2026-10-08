"""Verified provisioning preserves existing files on failure/cancellation."""
from dataclasses import replace
import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from commonUtils.downloads import DownloadSpec, DownloadCancelled, is_ready, provision


class Response(BytesIO):
    def __init__(self, content):
        super().__init__(content)
        self.headers = {'Content-Length': str(len(content))}
    def geturl(self):
        return 'https://example.test/release'


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'software/tool'
        self.payload = b'verified executable'
        stream = BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('release/tool', self.payload)
            archive.writestr('../unwanted', b'never extracted')
        self.archive = stream.getvalue()
        self.spec = DownloadSpec('Tool', '1', 'https://example.test/release.zip',
            hashlib.sha256(self.archive).hexdigest(), hashlib.sha256(self.payload).hexdigest(),
            'release/tool', True)

    def test_verified_zip_only_installs_expected_member_and_reuses_it(self):
        with patch('commonUtils.downloads.urlopen', return_value=Response(self.archive)) as fetch:
            self.assertEqual(provision(self.spec, self.path), self.path)
            self.assertEqual(self.path.read_bytes(), self.payload)
            self.assertTrue(is_ready(self.spec, self.path))
            provision(self.spec, self.path)
            fetch.assert_called_once()
        self.assertFalse((self.path.parent / 'unwanted').exists())
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_bad_archive_or_payload_hash_keeps_old_file(self):
        self.path.parent.mkdir()
        self.path.write_bytes(b'previous executable')
        for spec in (replace(self.spec, sha256='0'*64), replace(self.spec, installed_sha256='0'*64)):
            with patch('commonUtils.downloads.urlopen', return_value=Response(self.archive)):
                with self.assertRaisesRegex(ValueError, 'SHA-256'):
                    provision(spec, self.path)
            self.assertEqual(self.path.read_bytes(), b'previous executable')
            self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_cancellation_keeps_old_file(self):
        self.path.parent.mkdir()
        self.path.write_bytes(b'old')
        with patch('commonUtils.downloads.urlopen', return_value=Response(self.archive)):
            with self.assertRaises(DownloadCancelled):
                provision(self.spec, self.path, cancelled=lambda: True)
        self.assertEqual(self.path.read_bytes(), b'old')

    def test_direct_installer(self):
        spec = replace(self.spec, sha256=self.spec.installed_sha256, archive_member=None, executable=False)
        with patch('commonUtils.downloads.urlopen', return_value=Response(self.payload)):
            provision(spec, self.path)
        self.assertEqual(self.path.read_bytes(), self.payload)

    def test_missing_archive_member_is_rejected(self):
        stream = BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('other', self.payload)
        data = stream.getvalue()
        spec = replace(self.spec, sha256=hashlib.sha256(data).hexdigest())
        with patch('commonUtils.downloads.urlopen', return_value=Response(data)):
            with self.assertRaisesRegex(ValueError, 'expected executable'):
                provision(spec, self.path)
        self.assertFalse(self.path.exists())

    def test_cancel_before_download_never_connects_or_creates_workspace(self):
        with patch('commonUtils.downloads.urlopen') as fetch:
            with self.assertRaises(DownloadCancelled):
                provision(self.spec, self.path, cancelled=lambda: True)
        fetch.assert_not_called()
        self.assertFalse(self.path.parent.exists())

    def test_cancel_during_payload_extraction_preserves_previous_executable(self):
        from threading import Event
        from commonUtils import downloads
        cancelled = Event()
        self.path.parent.mkdir()
        self.path.write_bytes(b'previous executable')
        real_copy = downloads.copy_stream
        def copy(*args, **kwargs):
            cancelled.set()
            return real_copy(*args, **kwargs)
        with patch('commonUtils.downloads.urlopen', return_value=Response(self.archive)), \
                patch.object(downloads, 'copy_stream', side_effect=copy):
            with self.assertRaises(DownloadCancelled):
                provision(self.spec, self.path, cancelled=cancelled.is_set)
        self.assertEqual(self.path.read_bytes(), b'previous executable')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
