"""Search owners keep UI imports out of query and disk-search modules."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.search.files import search_files
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


class SearchFilesTests(unittest.TestCase):
    def test_masks_case_words_regex_exclusions_unicode_and_live_buffers(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            py, txt = root / 'code.py', root / 'notes.txt'
            py.write_text('😀 target target_other\nTARGET\n')
            txt.write_text('target\n')
            (root / 'binary.py').write_bytes(b'target\x00')
            (root / 'ignored').mkdir()
            (root / 'ignored' / 'skip.py').write_text('target\n')
            result = search_files([root], ['ignored'], 'target', '*.py', whole=True)
            self.assertEqual(len(result.hits), 2)
            self.assertEqual(result.files, 1)
            self.assertEqual((result.hits[0].line, result.hits[0].column, result.hits[0].start), (1, 2, 3))
            self.assertEqual(len(search_files([root], ['ignored'], 'target', '*.py', case=True, whole=True).hits), 1)
            self.assertEqual(len(search_files([root], ['ignored'], r'targ\w+', '*.py', regex=True).hits), 3)
            result = search_files([root], [], 'live', '*.txt', buffers={txt: 'unsaved live\n'})
            self.assertEqual(result.hits[0].path, txt)
            self.assertEqual(result.hits[0].column, 8)
            self.assertEqual(txt.read_text(), 'target\n')
            with self.assertRaises(ValueError):
                search_files([root], [], '(', regex=True)
            self.assertFalse(search_files([root], [], 'target', cancelled=lambda: True).hits)
            self.assertTrue(search_files([root], [], 'target', limit=1).limited)

    def test_excluded_directory_prefix_also_excludes_unsaved_buffers(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / 'src' / 'generated' / 'nested' / 'new.py'
            result = search_files([root], ['src/generated'], 'target',
                                  buffers={path: 'target'})
            self.assertFalse(result.hits)
            excluded = root / 'src' / 'generated'
            for search_root in (root, excluded):
                result = search_files([search_root], [], 'target', buffers={path: 'target'},
                                      exclude_path=lambda candidate, _: candidate == excluded)
                self.assertFalse(result.hits)


class IndexedFileSearchTests(unittest.TestCase):
    def setUp(self):
        from commonUtils.filesystem.index import DirectoryCache
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.root = base / 'project'
        (self.root / 'src').mkdir(parents=True)
        (self.root / 'ignored').mkdir()
        (self.root / 'src/code.py').write_text('old content')
        (self.root / 'ignored/skip.py').write_text('target')
        self.cache = DirectoryCache(database=base / 'index.sqlite3')
        self.addCleanup(self.cache.close)
        self.cache.get(self.root).close()

    def test_warm_names_avoid_enumeration_but_read_current_text_and_buffers(self):
        path = self.root / 'src/code.py'
        path.write_text('😀 target')
        draft = self.root / 'src/unsaved.py'
        with patch('os.scandir', side_effect=AssertionError('Unchanged folder enumerated')):
            result = search_files([self.root], ['ignored'], 'target', '*.py', cache=self.cache,
                                  buffers={draft: 'target draft'})
        self.assertEqual([hit.path for hit in result.hits], [path, draft])
        self.assertEqual(result.hits[0].start, 3)
        self.assertFalse(result.limited)

    def test_changed_and_new_folders_scan_while_unchanged_ancestors_reuse_index(self):
        old = self.root / 'src/code.py'
        old.rename(old.with_name('renamed.py'))
        (self.root / 'src/new').mkdir()
        (self.root / 'src/new/added.py').write_text('target')
        import os
        with patch('os.scandir', wraps=os.scandir) as scan:
            result = search_files([self.root], ['ignored'], 'target', cache=self.cache)
        self.assertEqual([hit.path for hit in result.hits], [self.root / 'src/new/added.py'])
        self.assertEqual([Path(call.args[0]) for call in scan.call_args_list],
                         [self.root / 'src', self.root / 'src/new'])

    def test_cached_and_live_candidates_keep_order_masks_limits_and_overlap(self):
        for name in ('a.py', 'b.txt', 'c.py'):
            (self.root / name).write_text('target')
        self.cache.get(self.root).close()
        for options in ({}, {'masks': '*.py'}, {'max_files': 1}, {'max_entries': 2},
                        {'limit': 1}, {'cancelled': lambda: True}):
            with self.subTest(options=options):
                roots = [self.root, self.root / 'src']
                live = search_files(roots, ['ignored'], 'target', **options)
                cached = search_files(roots, ['ignored'], 'target', cache=self.cache, **options)
                self.assertEqual(cached, live)

    def test_replaced_folder_link_is_not_followed(self):
        import shutil
        outside = self.root.parent / 'outside'
        outside.mkdir()
        (outside / 'secret.py').write_text('target')
        shutil.rmtree(self.root / 'src')
        try:
            (self.root / 'src').symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(str(error))
        self.assertFalse(search_files([self.root], ['ignored'], 'target', cache=self.cache).hits)

    def test_unfinished_checkpoint_and_broken_cache_fall_back_to_live_names(self):
        import sqlite3
        with sqlite3.connect(self.cache.database) as connection:
            connection.execute("UPDATE folders SET status='pending' WHERE path=?", (str(self.root / 'src'),))
        import os
        with patch('os.scandir', wraps=os.scandir) as scan:
            result = search_files([self.root], ['ignored'], 'old', cache=self.cache)
        self.assertEqual(len(result.hits), 1)
        self.assertEqual([Path(call.args[0]) for call in scan.call_args_list], [self.root / 'src'])
        with patch.object(self.cache, 'peek', side_effect=sqlite3.DatabaseError('unavailable')):
            self.assertEqual(search_files([self.root], ['ignored'], 'old', cache=self.cache), result)

    def test_index_exclusions_and_recorded_errors_cannot_hide_live_candidates(self):
        from commonUtils.filesystem.index import DirectoryCache
        storage = self.root / 'cache'
        storage.mkdir()
        (storage / 'visible.py').write_text('target')
        with DirectoryCache(database=storage / 'index.sqlite3') as cache:
            cache.get(self.root).close()
            result = search_files([self.root], ['ignored'], 'target', '*.py', cache=cache)
        self.assertEqual([hit.path for hit in result.hits], [storage / 'visible.py'])
        import sqlite3
        with sqlite3.connect(self.cache.database) as connection:
            generation = connection.execute('SELECT completed FROM roots WHERE root=?',
                                            (str(self.root),)).fetchone()[0]
            connection.execute('INSERT INTO errors VALUES(?,?,?)',
                               (generation, str(self.root / 'src/code.py'), 'previous metadata failure'))
        import os
        with patch('os.scandir', wraps=os.scandir) as scan:
            result = search_files([self.root / 'src'], [], 'old', cache=self.cache)
        self.assertEqual(len(result.hits), 1)
        self.assertEqual([Path(call.args[0]) for call in scan.call_args_list], [self.root / 'src'])
