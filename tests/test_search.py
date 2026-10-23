"""Search owners keep UI imports out of query and disk-search modules."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from commonUtils.search.text import contains_text, literal_pattern


class SearchBoundaryTests(unittest.TestCase):
    def test_literal_queries_preserve_native_and_catalog_semantics(self):
        self.assertIsNone(literal_pattern(''))
        self.assertEqual(literal_pattern('a.b').findall('a.b A.B axb'), ['a.b', 'A.B'])
        self.assertEqual(literal_pattern('a.b', case=True).findall('A.B a.b'), ['a.b'])
        self.assertTrue(contains_text('Straße notes', 'STRASSE'))
        self.assertFalse(contains_text('Straße notes', 'STRASSE', case=True))

    def test_imports_are_lazy_and_vendored_owners_are_independent(self):
        subprocess.run([sys.executable, '-c', '''
import importlib, sys, types
from pathlib import Path
import commonUtils
vendor = types.ModuleType('_search_vendor')
vendor.__path__ = [str(Path(commonUtils.__file__).parent.parent)]
sys.modules[vendor.__name__] = vendor
for name in ('names', 'text', 'providers', 'indexed', 'files'):
    a = importlib.import_module('commonUtils.search.' + name)
    b = importlib.import_module('_search_vendor.commonUtils.search.' + name)
    assert a is not b
assert not any(name.startswith(('PySide6', 'toga')) for name in sys.modules)
from commonUtils.search.qt_text import find_matches
assert find_matches('😀 cat', 'cat')[0][0].start == 3
assert not any(name.startswith(('PySide6.QtWidgets', 'commonUtils.ui')) for name in sys.modules)
'''], check=True)

    def test_text_file_search_obeys_caller_limits_and_keeps_disk_bytes(self):
        from commonUtils.search.files import search_files
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = root / 'note.txt'
            path.write_text('disk content')
            result = search_files([root], [], 'draft', buffers={path: '😀 draft'})
            self.assertEqual((result.hits[0].column, result.hits[0].start), (2, 3))
            self.assertEqual(path.read_text(), 'disk content')
            self.assertFalse(search_files([root], [], 'disk', max_file_size=2).hits)
            self.assertFalse(search_files([root], [], 'draft', buffers={path: 'long draft'}, max_file_size=2).hits)
