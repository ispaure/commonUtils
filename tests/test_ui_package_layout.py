"""UI grouping preserves direct imports, patch targets and vendored isolation."""
import subprocess
import sys
import unittest


class UIPackageLayoutTests(unittest.TestCase):
    def run_script(self, script):
        subprocess.run([sys.executable, '-c', script], check=True)

    def test_groups_do_not_eagerly_import_qt_or_change_import_finders(self):
        self.run_script('''
import importlib, sys
from pathlib import Path
import commonUtils
root = Path(commonUtils.__file__).parent / 'ui'
finders = tuple(sys.meta_path)
for group in ('workspaces', 'tasks', 'readers', 'settings', 'appearance'):
    if (root / group).is_dir():
        importlib.import_module('commonUtils.ui.' + group)
assert tuple(sys.meta_path) == finders
assert not any(name.startswith('PySide6') for name in sys.modules)
''')

    def test_old_and_canonical_imports_share_modules_in_both_orders(self):
        for canonical_first in (False, True):
            with self.subTest(canonical_first=canonical_first):
                self.run_script(f'''
import importlib, sys, types
from pathlib import Path
from unittest.mock import patch
import commonUtils
root = Path(commonUtils.__file__).parent
vendor = types.ModuleType('_ui_vendor')
vendor.__path__ = [str(root.parent)]
sys.modules[vendor.__name__] = vendor
pairs = []
for group in ('workspaces', 'tasks', 'readers', 'settings', 'appearance'):
    for path in sorted((root / 'ui' / group).glob('*.py')):
        if path.stem != '__init__':
            pairs.append((path.stem, group + '.' + path.stem))
for namespace in ('commonUtils', '_ui_vendor.commonUtils'):
    for old, new in pairs:
        old_name = namespace + '.ui.' + old
        new_name = namespace + '.ui.' + new
        first, second = (new_name, old_name) if {canonical_first!r} else (old_name, new_name)
        implementation = importlib.import_module(first)
        assert importlib.import_module(second) is implementation, (first, second)
        assert implementation.__spec__.name == new_name
        parent = importlib.import_module(namespace + '.ui')
        assert getattr(parent, old) is implementation
        marker = object()
        with patch(old_name + '._compat_test_marker', marker, create=True):
            assert getattr(importlib.import_module(new_name), '_compat_test_marker') is marker
        if namespace.startswith('_ui_vendor'):
            assert implementation is not importlib.import_module('commonUtils.ui.' + new)
# Stateful registries must stay in their namespace, rather than a standalone alias.
for old, new in pairs:
    standalone = importlib.import_module('commonUtils.ui.' + new)
    vendored = importlib.import_module('_ui_vendor.commonUtils.ui.' + new)
    for field in ('_workspaces', '_docks', '_windows'):
        if hasattr(standalone, field):
            assert getattr(standalone, field) is not getattr(vendored, field)
''')
