"""Archive formats use shared file resolution and passive detail hooks."""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import unittest

from commonUtils import archives
from commonUtils.fileUtils import File
from commonUtils.fileTypes.archiveType import ArchiveFile
from commonUtils.fileTypes.zipType import ZIPFile
from commonUtils.fileTypes.registry import file_from_path


class ArchiveTypeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'notes.txt'
        self.source.write_text('Hello archive')

    def test_compound_tar_suffixes_resolve_without_claiming_plain_gzip(self):
        for suffix in archives.TAR_SUFFIXES:
            self.assertIs(type(file_from_path(self.root / ('backup' + suffix))), ArchiveFile)
        self.assertIs(type(file_from_path(self.root / 'notes.gz')), File)
        self.assertIs(type(file_from_path(self.root / 'notes.xz')), File)
        self.assertIsInstance(file_from_path(self.root / 'backup.zip'), ZIPFile)
        self.assertIsInstance(file_from_path(self.root / 'backup.zip'), ArchiveFile)

    def test_encrypted_details_do_not_require_or_prompt_for_a_password(self):
        path = self.root / 'encrypted.zip'
        archives.create([self.source], path, password='test-secret')
        file = file_from_path(path)
        panel, = file.browser_panels()
        self.assertEqual(panel.key, 'archive.contents')
        details = panel.load()
        self.assertEqual(dict(details.fields)['Files'], '1')
        self.assertEqual(dict(details.fields)['Protection'], 'Encrypted file contents')
        self.assertIn('notes.txt', details.message)
        self.assertNotIn('test-secret', str(details))

    def test_tar_details_and_shared_selected_extraction(self):
        path = self.root / 'backup.tar.gz'
        archives.create([self.source], path, format='tar.gz')
        file = file_from_path(path)
        self.assertEqual(file.archive_entries()[0].name, 'notes.txt')
        file.extract_to_new_directory(self.root / 'out', selected=['notes.txt'])
        self.assertEqual((self.root / 'out' / 'notes.txt').read_text(), 'Hello archive')
        self.assertEqual(dict(file.browser_panels()[0].load().fields)['Files'], '1')

    def test_importing_format_declarations_does_not_load_qt_or_crypto(self):
        code = ('import sys; from commonUtils.archives import is_supported_archive; '
                'from commonUtils.fileTypes.archiveType import ArchiveFile; '
                'assert is_supported_archive("example.TAR.GZ"); '
                'assert "pyzipper" not in sys.modules; '
                'assert not any(name.startswith("PySide6") for name in sys.modules)')
        completed = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
