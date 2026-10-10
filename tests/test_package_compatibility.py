"""Legacy imports must share implementation state after package reorganization."""
import importlib
from pathlib import Path
import tempfile
import unittest


class PackageCompatibilityTests(unittest.TestCase):
    def test_public_aliases_share_modules_and_singletons(self):
        for old, new in [('directory_index', 'directory'), ('text_files', 'persistence.text'),
                         ('session_store', 'persistence.session')]:
            with self.subTest(module=old):
                legacy = importlib.import_module('commonUtils.' + old)
                canonical = importlib.import_module('commonUtils.' + new)
                self.assertIs(legacy, canonical)
        from commonUtils import directory, directory_index
        self.assertIs(directory.directory_cache, directory_index.directory_cache)

    def test_moved_writer_and_scanner_work_together(self):
        from commonUtils.directory import scan_metadata
        from commonUtils.persistence import atomic_write_bytes
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.txt'
            atomic_write_bytes(path, b'content')
            snapshot = scan_metadata(Path(folder))
            self.assertEqual([entry.path for entry in snapshot.entries], [path])
