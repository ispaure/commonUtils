"""Direct package imports, isolated namespaces and library-relative data paths."""
import importlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from commonUtils.filesystem import files
from commonUtils.configuration.settings import settings_path


class PackageLayoutTests(unittest.TestCase):
    def test_source_relative_locations_survive_packaging(self):
        root = Path(importlib.import_module('commonUtils').__file__).resolve().parent
        self.assertEqual(files.get_current_working_dir(), root.parent)
        self.assertEqual(settings_path(), root / 'ui' / 'settings.ini')

    def test_writer_and_scanner_work_together(self):
        from commonUtils.filesystem.index import scan_metadata
        from commonUtils.persistence import atomic_write_bytes
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.txt'
            atomic_write_bytes(path, b'content')
            snapshot = scan_metadata(Path(folder))
            self.assertEqual([entry.path for entry in snapshot.entries], [path])

    def test_root_import_is_lazy_and_leaves_import_machinery_untouched(self):
        script = """
import sys
finders = tuple(sys.meta_path)
import commonUtils
assert tuple(sys.meta_path) == finders
assert '__getattr__' not in vars(commonUtils)
assert not any(name.startswith('PySide6') for name in sys.modules)
assert not any(name.startswith('commonUtils.') for name in sys.modules)
"""
        subprocess.run([sys.executable, '-c', script], check=True)

    def test_vendored_namespace_has_independent_modules_and_registry(self):
        script = """
import importlib, sys, types
from pathlib import Path
import commonUtils
root = Path(commonUtils.__file__).resolve().parent
vendor = types.ModuleType('_vendor')
vendor.__path__ = [str(root.parent)]
sys.modules['_vendor'] = vendor
vendored = importlib.import_module('_vendor.commonUtils')
for name in ('runtime.platform', 'formats.registry', 'filesystem.index.metadata',
             'integrations.wrappers.cmdShellWrapper.command', 'ui.native.dialogs', 'runtime.resources.provider',
             'runtime.resources.local', 'runtime.resources.selection'):
    module = importlib.import_module('_vendor.commonUtils.' + name)
    standalone = importlib.import_module('commonUtils.' + name)
    assert module is not standalone
    assert module.__spec__.name == '_vendor.commonUtils.' + name
    assert importlib.reload(module) is module
from commonUtils.formats.registry import file_types
from _vendor.commonUtils.formats.registry import file_types as vendored_types
assert vendored_types is not file_types
assert not any(name.startswith('PySide6') for name in sys.modules)
"""
        subprocess.run([sys.executable, '-c', script], check=True)
