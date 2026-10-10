"""Relocated packages preserve state and library-relative data locations."""
import importlib
from pathlib import Path
import unittest
from commonUtils.filesystem import files as fileUtils
from commonUtils.configuration.settings import settings_path

class PackageLayoutTests(unittest.TestCase):
    def test_canonical_and_compatibility_imports_share_state(self):
        for old,new in [('file_operations','filesystem.transfers'),('file_removal','filesystem.removal'),
                        ('traversal','filesystem.traversal'),('network_filesystems','filesystem.network'),
                        ('downloads','streams.downloads'),('zip_access','archives.zip_access'),('settings','configuration.settings')]:
            with self.subTest(old=old):
                self.assertIs(importlib.import_module('commonUtils.'+old),importlib.import_module('commonUtils.'+new))

    def test_source_relative_locations_survive_packaging(self):
        root=Path(__import__("commonUtils").__file__).resolve().parent
        self.assertEqual(fileUtils.get_current_working_dir(),root.parent)
        self.assertEqual(settings_path(),root/'ui'/'settings.ini')

    def test_nested_aliases_and_reload_share_identity(self):
        for old, new in [('fileTypes.jsonType', 'formats.jsonType'),
                         ('wrappers.cmdShellWrapper.command', 'integrations.wrappers.cmdShellWrapper.command'),
                         ('directory.metadata', 'filesystem.index.metadata')]:
            with self.subTest(old=old):
                legacy = importlib.import_module('commonUtils.' + old)
                canonical = importlib.import_module('commonUtils.' + new)
                self.assertIs(legacy, canonical)
                self.assertEqual(legacy.__spec__.name, 'commonUtils.' + new)
                self.assertIs(importlib.reload(legacy), canonical)

    def test_canonical_and_legacy_class_references(self):
        legacy = importlib.import_module('commonUtils.fileTypes.jsonType')
        canonical = importlib.import_module('commonUtils.formats.jsonType')
        self.assertIs(legacy.JSONFile, canonical.JSONFile)

    def test_vendored_namespace_is_independent_and_lazy(self):
        import subprocess
        import sys
        script = '''
import importlib, sys, types
from pathlib import Path
import commonUtils
root = Path(commonUtils.__file__).resolve().parent
vendor = types.ModuleType('_vendor')
vendor.__path__ = [str(root.parent)]
sys.modules['_vendor'] = vendor
vendored = importlib.import_module('_vendor.commonUtils')
assert not any(name.startswith('PySide6') for name in sys.modules)
for old, new in [('osUtils', 'runtime.platform'),
                 ('wrappers.piexifWrapper', 'integrations.wrappers.piexifWrapper'),
                 ('directory.metadata', 'filesystem.index.metadata'),
                 ('wrappers.cmdShellWrapper.command', 'integrations.wrappers.cmdShellWrapper.command')]:
    alias = importlib.import_module('_vendor.commonUtils.' + old)
    canonical = importlib.import_module('_vendor.commonUtils.' + new)
    standalone = importlib.import_module('commonUtils.' + new)
    assert alias is canonical
    assert alias is not standalone
    assert alias.__spec__.name == '_vendor.commonUtils.' + new
'''
        subprocess.run([sys.executable, '-c', script], check=True)
