"""OS conventions, scoped cleanup and WAL-safe index migration."""
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.storage import cache_directory, temporary_directory, temporary_workspace
from commonUtils.directory_index import DirectoryCache
from commonUtils.operations import OperationCancelled


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.home_patch = patch.object(Path, 'home', return_value=self.home)
        self.home_patch.start(); self.addCleanup(self.home_patch.stop)

    def test_platform_paths_and_relative_xdg_fallback(self):
        for platform, env, expected in [
            ('darwin', {}, self.home/'Library'/'Caches'),
            ('win32', {'LOCALAPPDATA': str(self.home/'Local')}, self.home/'Local'),
            ('win32', {}, self.home/'AppData'/'Local'),
            ('linux', {'XDG_CACHE_HOME': str(self.home/'custom')}, self.home/'custom'),
            ('linux', {'XDG_CACHE_HOME': 'relative'}, self.home/'.cache'),
            ('linux', {}, self.home/'.cache')]:
            with self.subTest(platform=platform, env=env), patch('commonUtils.storage.sys.platform', platform), patch.dict(os.environ, env, clear=True):
                expected=expected/'commonUtils'
                self.assertEqual(cache_directory(create=False), expected)
                self.assertEqual(temporary_directory(create=False), expected/'Temp')
                self.assertEqual(temporary_directory(), expected/'Temp')
                self.assertTrue((expected/'Temp').is_dir())

    def test_workspace_cleanup_keeps_persistent_data(self):
        with patch('commonUtils.storage.sys.platform', 'darwin'):
            persistent = cache_directory()/'saved'; persistent.write_bytes(b'cache')
            with temporary_workspace() as folder:
                workspace=Path(folder); (workspace/'file').write_text('temporary')
                self.assertEqual(workspace.parent, temporary_directory())
                if os.name == 'posix': self.assertEqual(workspace.stat().st_mode & 0o777, 0o700)
            self.assertFalse(workspace.exists())
            self.assertTrue(persistent.exists())

    def test_migration_includes_wal_and_preserves_old_file(self):
        root=self.home/'files'; root.mkdir(); (root/'a.txt').write_text('content')
        old=self.home/'Library'/'Application Support'/'commonUtils'/'directory-index.sqlite3'
        snapshot=DirectoryCache(database=old).get(root)
        # Open readers keep the source WAL alive; backup must copy logical contents.
        with patch('commonUtils.storage.sys.platform', 'darwin'):
            new=DirectoryCache()
            self.assertFalse(new.database.exists())
            reused=new.get(root)
            self.assertTrue(reused.reused)
            self.assertEqual(tuple(reused.entries), tuple(snapshot.entries))
            self.assertTrue(old.exists())
            (root/'b.txt').write_text('new')
            new.get(root)
            restarted=DirectoryCache().get(root)
            self.assertEqual(len(restarted.entries), 2)
            self.assertEqual(len(snapshot.entries), 1)

    def test_cancelled_migration_leaves_no_destination_or_temporary(self):
        old=self.home/'old.sqlite3'; old.parent.mkdir(exist_ok=True)
        with sqlite3.connect(old) as db: db.execute('CREATE TABLE example(value)')
        new=DirectoryCache(database=self.home/'new.sqlite3'); new._legacy_database=old
        with self.assertRaises(OperationCancelled): new._migrate_legacy(lambda: True)
        self.assertFalse(new.database.exists())
        self.assertFalse(list(self.home.glob('.index-migration-*')))
        self.assertTrue(old.exists())
