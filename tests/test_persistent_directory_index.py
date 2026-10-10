"""Durable folder checkpoints, snapshot isolation and incremental directory updates."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import patch

from commonUtils.directory import DirectoryCache, directory_index_path, storage_totals
from commonUtils.operations import OperationCancelled


class PersistentIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.root = self.folder / 'files'
        self.root.mkdir()
        self.database = self.folder / 'support' / 'directory-index.sqlite3'
        self.cache = DirectoryCache(database=self.database)
        self.addCleanup(self.cache.close)
        for name in ('aaa', 'bbb'):
            (self.root / name).mkdir()
            (self.root / name / 'file.txt').write_text(name)

    def pause(self, *, refresh=False, folder='aaa'):
        cancel = Event()
        def report(done, total, message):
            if message == f'Indexing {self.root / folder}':
                cancel.set()
        with self.assertRaises(OperationCancelled):
            self.cache.get(self.root, refresh=refresh, cancelled=cancel.is_set, report=report)
        return self.cache.status(self.root)

    def test_path_defaults_to_cache_on_macos(self):
        with patch('commonUtils.directory.store.sys.platform', 'darwin'), patch.object(Path, 'home', return_value=self.folder):
            self.assertEqual(directory_index_path(), self.folder / 'Library' / 'Application Support' / 'commonUtils' / 'Cache' / 'directory-index.sqlite3')

    def test_completed_index_survives_new_instance_without_reenumeration(self):
        original = self.cache.get(self.root)
        with DirectoryCache(database=self.database) as restarted:
            with patch('commonUtils.directory.os.scandir', side_effect=AssertionError('Unexpected enumeration')):
                reused = restarted.get(self.root)
            self.assertTrue(reused.reused)
            self.assertEqual(reused.scanned_at, original.scanned_at)
            self.assertEqual(tuple(reused.entries), tuple(original.entries))
            self.assertEqual(storage_totals(reused)[self.root], 6)

    def test_cancelled_scan_resumes_completed_folders_after_restart(self):
        saved = self.pause()
        self.assertEqual(saved['folders_done'], 2)
        self.assertEqual(saved['folders_remaining'], 1)
        original = __import__('os').scandir
        seen = []
        def scandir(path):
            seen.append(Path(path))
            return original(path)
        with patch('commonUtils.directory.os.scandir', side_effect=scandir):
            result = DirectoryCache(database=self.database).get(self.root)
        self.assertTrue(result.resumed)
        self.assertTrue(result.complete)
        self.assertEqual(seen, [self.root / 'bbb'])
        self.assertEqual(len(result.entries), 4)
        self.assertIsNone(self.cache.status(self.root))

    def test_changed_and_deleted_checkpoints_are_reconciled_before_resuming(self):
        self.pause()
        (self.root / 'aaa' / 'new.txt').write_text('new')
        (self.root / 'bbb' / 'file.txt').unlink()
        (self.root / 'bbb').rmdir()
        result = self.cache.get(self.root)
        self.assertTrue(result.resumed)
        self.assertEqual({entry.path.relative_to(self.root).as_posix() for entry in result.entries},
                         {'aaa', 'aaa/file.txt', 'aaa/new.txt'})

    def test_mid_folder_cancellation_reenumerates_the_incomplete_folder(self):
        for name in ('1.txt', '2.txt', '3.txt'):
            (self.root / 'aaa' / name).write_text(name)
        saved = self.pause()
        self.assertEqual(saved['folders_done'], 1)
        result = self.cache.get(self.root)
        self.assertTrue(result.complete)
        self.assertEqual(len(result.entries), 7)
        self.assertEqual(len({entry.path for entry in result.entries}), 7)

    def test_cancelled_rebuild_preserves_previous_complete_snapshot(self):
        old = self.cache.get(self.root)
        (self.root / 'aaa' / 'file.txt').write_text('updated file')
        self.pause(refresh=True)
        self.assertEqual(old.search('file')[0].size, 3)
        result = self.cache.get(self.root)
        self.assertTrue(result.resumed)
        self.assertEqual(result.search('file')[0].size, 12)
        # Superseded generations remain readable while their old results are open.
        self.assertEqual(old.search('file')[0].size, 3)

    def test_refresh_discards_partial_and_clear_preserves_open_results(self):
        self.pause()
        rebuilt = self.cache.get(self.root, refresh=True)
        self.assertFalse(rebuilt.resumed)
        self.assertTrue(rebuilt.complete)
        self.cache.clear(self.root)
        self.assertIsNone(self.cache.status(self.root))
        self.assertEqual(len(rebuilt.search('file')), 2)
        result = self.cache.get(self.root)
        self.assertFalse(result.reused)
        self.assertFalse(result.resumed)

    def test_unreadable_folders_remain_partial_and_are_retried(self):
        original = __import__('os').scandir
        def unreadable(path):
            if Path(path) == self.root / 'aaa':
                raise PermissionError('temporarily locked')
            return original(path)
        with patch('commonUtils.directory.os.scandir', side_effect=unreadable):
            result = self.cache.get(self.root)
        self.assertFalse(result.complete)
        self.assertIn('temporarily locked', result.errors[0][1])
        self.assertIsNotNone(self.cache.status(self.root))
        retried = self.cache.get(self.root)
        self.assertTrue(retried.complete)
        self.assertTrue(retried.resumed)
        self.assertEqual(retried.errors, ())

    def test_replaced_directory_link_is_not_followed_on_resume(self):
        self.pause()
        (self.root / 'aaa' / 'file.txt').unlink()
        (self.root / 'aaa').rmdir()
        (self.root / 'aaa').symlink_to(self.root / 'bbb', target_is_directory=True)
        result = self.cache.get(self.root)
        links = [entry for entry in result.entries if entry.path == self.root / 'aaa']
        self.assertTrue(links[0].symlink)
        self.assertEqual(len(result.entries), 3)

    def test_unicode_literal_search_and_natural_order(self):
        for name in ('10.txt', '2.txt', 'Straße%_.txt'):
            (self.root / name).write_text(name)
        result = self.cache.get(self.root)
        self.assertEqual(result.search('STRASSE%_')[0].path.name, 'Straße%_.txt')
        names = [entry.path.name for entry in result.entries]
        self.assertLess(names.index('2.txt'), names.index('10.txt'))
        with self.assertRaises(OperationCancelled):
            result.search('file', cancelled=lambda: True)

    def test_name_search_checks_folders_and_storage_reconciles_file_sizes(self):
        self.cache.get(self.root)
        file = self.root / 'aaa' / 'file.txt'
        file.write_text('larger contents')
        original = Path.lstat
        def stat(path, *args, **kwargs):
            if path == file:
                raise AssertionError('Name-only cache reuse should not stat every file')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', stat):
            names = self.cache.get(self.root, validate_files=False)
        self.assertTrue(names.reused)
        self.assertFalse(names.metadata_checked)
        self.assertEqual(names.search('file')[0].size, 3)
        storage = self.cache.get(self.root)
        self.assertEqual(storage.search('file')[0].size, 15)

    def test_waiting_writer_can_cancel_without_disturbing_active_scan(self):
        entered, release, cancel, finished = Event(), Event(), Event(), Event()
        errors = []
        def report(done, total, message):
            if message.startswith('Indexing') and not entered.is_set():
                entered.set(); release.wait(3)
        def scan():
            try:
                self.cache.get(self.root, report=report)
            except Exception as error:
                errors.append(error)
        def waiting_scan():
            try:
                DirectoryCache(database=self.database).get(self.root, cancelled=cancel.is_set)
            except OperationCancelled:
                finished.set()
            except Exception as error:
                errors.append(error)
        worker = Thread(target=scan)
        waiting = Thread(target=waiting_scan)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            waiting.start(); cancel.set()
            self.assertTrue(finished.wait(2))
        finally:
            release.set(); worker.join(3)
            if waiting.ident is not None:
                waiting.join(3)
        self.assertEqual(errors, [])
        self.assertIsNone(self.cache.status(self.root))

    def test_index_storage_is_excluded_when_scanning_its_parent(self):
        result = self.cache.get(self.folder)
        self.assertFalse(any(entry.path == self.database.parent for entry in result.entries))
        with self.assertRaisesRegex(ValueError, 'cannot index itself'):
            self.cache.get(self.database.parent)

    def test_lexical_symlink_root_detects_membership_changes(self):
        alias = self.folder / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        first = self.cache.get(alias)
        self.assertTrue(all(entry.path.is_relative_to(alias) for entry in first.entries))
        (self.root / 'added.txt').write_text('new')
        changed = self.cache.get(alias, validate_files=False)
        self.assertFalse(changed.reused)
        self.assertEqual(changed.search('added')[0].path, alias / 'added.txt')

    def test_index_exceeds_old_entry_limit_without_loading_every_entry(self):
        count = 200_005
        info = (self.root / 'aaa' / 'file.txt').lstat()
        original_stat = Path.lstat
        class Child:
            def __init__(self, index):
                self.path = str(self.root / f'virtual{index}.txt')
            root = self.root
            def stat(self, *, follow_symlinks): return info
            def is_symlink(self): return False
            def is_dir(self, *, follow_symlinks): return False
        @contextmanager
        def children(folder):
            yield (Child(index) for index in range(count))
        def stat(path, *args, **kwargs):
            return info if path.name.startswith('virtual') else original_stat(path, *args, **kwargs)
        with patch('commonUtils.directory.os.scandir', children), patch.object(Path, 'lstat', stat):
            result = self.cache.get(self.root)
            self.assertTrue(result.complete)
            self.assertEqual(len(result.entries), count)
            self.assertNotIsInstance(result.entries, (list, tuple))
            self.assertEqual(result.search('virtual200004')[0].path.name, 'virtual200004.txt')
            page, total = result.search_page('virtual', offset=200_000, limit=500)
            self.assertEqual(total, count)
            self.assertEqual(len(page), 5)
            self.assertTrue(DirectoryCache(database=self.database).get(self.root).reused)
