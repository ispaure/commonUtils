"""Grouped UI imports are direct, lazy at package level and namespace-isolated."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import subprocess
import sys
import unittest


GROUPS = {
    'workspaces': ('workspace', 'workspace_drag', 'workspace_layout', 'workspace_window',
                   'workspace_policy', 'workspace_menus', 'workspace_cocoa', 'scoped_tabs'),
    'tasks': ('operations', 'operation_progress', 'process_runner', 'process_progress',
              'process_host', 'download'),
    'readers': ('reader_chrome', 'reader_menus', 'read_aloud', 'page_wheel'),
    'settings': ('ini_editor', 'layered_settings', 'settings_sections', 'font_preview'),
    'appearance': ('theme', 'styling', 'icons'),
}


class UIPackageLayoutTests(unittest.TestCase):
    def run_script(self, script):
        subprocess.run([sys.executable, '-c', script], check=True)

    def test_groups_do_not_eagerly_import_qt_or_change_import_finders(self):
        self.run_script(f'''
import importlib, sys
finders = tuple(sys.meta_path)
for group in {tuple(GROUPS)!r}:
    importlib.import_module('commonUtils.ui.' + group)
assert tuple(sys.meta_path) == finders
assert not any(name.startswith('PySide6') for name in sys.modules)
''')

    def test_flat_entry_points_are_removed_in_standalone_and_vendored_namespaces(self):
        self.run_script(f'''
import importlib, importlib.util, sys, types
from pathlib import Path
import commonUtils
root = Path(commonUtils.__file__).parent
vendor = types.ModuleType('_ui_vendor')
vendor.__path__ = [str(root.parent)]
sys.modules[vendor.__name__] = vendor
for namespace in ('commonUtils', '_ui_vendor.commonUtils'):
    parent = importlib.import_module(namespace + '.ui')
    for names in {GROUPS!r}.values():
        for name in names:
            removed = namespace + '.ui.' + name
            assert importlib.util.find_spec(removed) is None, removed
            try:
                importlib.import_module(removed)
            except ModuleNotFoundError as error:
                assert error.name == removed, error
            else:
                raise AssertionError(removed)
            assert name not in vars(parent), removed
assert not any(name.startswith('PySide6') for name in sys.modules)
''')

    def test_grouped_modules_and_registries_are_namespace_isolated(self):
        self.run_script(f'''
import importlib, sys, types
from pathlib import Path
import commonUtils
root = Path(commonUtils.__file__).parent
vendor = types.ModuleType('_ui_vendor')
vendor.__path__ = [str(root.parent)]
sys.modules[vendor.__name__] = vendor
for group, names in {GROUPS!r}.items():
    for name in names:
        canonical = '.ui.' + group + '.' + name
        standalone = importlib.import_module('commonUtils' + canonical)
        vendored = importlib.import_module('_ui_vendor.commonUtils' + canonical)
        assert standalone is not vendored
        assert standalone.__spec__.name == 'commonUtils' + canonical
        assert vendored.__spec__.name == '_ui_vendor.commonUtils' + canonical
        for field in ('_workspaces', '_docks', '_windows'):
            if hasattr(standalone, field):
                assert getattr(standalone, field) is not getattr(vendored, field)
        for namespace in ('commonUtils', '_ui_vendor.commonUtils'):
            assert namespace + '.ui.' + name not in sys.modules
''')

    def test_merge_ui_imports_the_persistence_owner_without_a_shim(self):
        self.run_script("""
import importlib, importlib.util
model = importlib.import_module('commonUtils.persistence.merge')
widget = importlib.import_module('commonUtils.ui.code_editor.merge')
assert widget.MergeSession is model.MergeSession
assert importlib.util.find_spec('commonUtils.ui.code_editor.merge_model') is None
""")
