"""Relocated packages preserve state and library-relative data locations."""
import importlib
from pathlib import Path
import unittest
from commonUtils import fileUtils
from commonUtils.configuration.settings import settings_path

class PackageLayoutTests(unittest.TestCase):
    def test_canonical_and_compatibility_imports_share_state(self):
        for old,new in [('file_operations','filesystem.transfers'),('file_removal','filesystem.removal'),
                        ('traversal','filesystem.traversal'),('network_filesystems','filesystem.network'),
                        ('downloads','streams.downloads'),('zip_access','archives.zip_access'),('settings','configuration.settings')]:
            with self.subTest(old=old):
                self.assertIs(importlib.import_module('commonUtils.'+old),importlib.import_module('commonUtils.'+new))

    def test_source_relative_locations_survive_packaging(self):
        root=Path(fileUtils.__file__).resolve().parents[1]
        self.assertEqual(fileUtils.get_current_working_dir(),root.parent)
        self.assertEqual(settings_path(),root/'ui'/'settings.ini')
