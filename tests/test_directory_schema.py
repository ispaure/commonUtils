"""Compact index migration, shared versions, and recovery against real SQLite."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.directory_index import DirectoryCache
from commonUtils._directory_order import _sort_key
from commonUtils._directory_schema import upgrade_entries, ensure_folder, initialize_schema
from commonUtils.operations import OperationCancelled


class DirectorySchemaTests(unittest.TestCase):
    def legacy(self, database):
        db = sqlite3.connect(database)
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
            CREATE TABLE scans(id INTEGER PRIMARY KEY,root TEXT,recursive INTEGER,scanned_at REAL);
            CREATE TABLE folders(generation INTEGER,path TEXT,parent TEXT,status TEXT,identity TEXT);
            CREATE TABLE entries(generation INTEGER,path TEXT,parent TEXT,name_fold TEXT,
                directory INTEGER,size INTEGER,modified INTEGER,symlink INTEGER,identity TEXT,sort_key BLOB,
                PRIMARY KEY(generation,path));
            CREATE TABLE roots(root TEXT,recursive INTEGER,completed INTEGER,building INTEGER);
            CREATE TABLE errors(generation INTEGER,path TEXT,error TEXT);
            PRAGMA user_version=2;
        ''')
        return db

    def test_upgrade_keeps_wal_data_partial_generations_and_recovery_copy(self):
        with TemporaryDirectory() as temporary:
            database = Path(temporary) / 'index.sqlite3'
            root = Path(temporary) / 'folder9'
            paths = [root / name for name in ('2.cbz', 'File10.TXT', 'file2.txt', 'Résumé.cbz', '100%_literal')]
            with closing(self.legacy(database)) as db:
                for generation in (1, 2):
                    db.execute('INSERT INTO scans VALUES(?,?,1,123)', (generation, str(root)))
                    db.execute("INSERT INTO folders VALUES(?,?,?,'pending',NULL)",
                               (generation, str(root), str(root.parent)))
                    db.executemany('INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?)',
                        [(generation, str(path), str(root), path.name.casefold(), 0, 10, 20, 0,
                          json.dumps([1, 2, 3]), _sort_key(path)) for path in paths])
                db.commit()
                self.assertTrue(Path(str(database) + '-wal').exists())
                upgrade_entries(db)
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 3)
                self.assertEqual(db.execute('SELECT count(*) FROM generation_entries').fetchone()[0], 10)
                self.assertEqual(db.execute('SELECT count(*) FROM entry_records').fetchone()[0], 5)
                self.assertEqual(db.execute('SELECT count(*) FROM entry_nodes').fetchone()[0], 5)
                self.assertEqual(db.execute('SELECT status FROM folders LIMIT 1').fetchone()[0], 'pending')
                for path, key in db.execute('SELECT path,sort_key FROM entries'):
                    self.assertEqual(key, _sort_key(path))
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
                backup = database.with_suffix('.pre-v3.sqlite3')
                with closing(sqlite3.connect(backup)) as recovery:
                    self.assertEqual(recovery.execute('PRAGMA user_version').fetchone()[0], 2)
                    self.assertEqual(recovery.execute('SELECT count(*) FROM entries').fetchone()[0], 10)
                stamp = backup.stat().st_mtime_ns
                upgrade_entries(db)
                self.assertEqual(backup.stat().st_mtime_ns, stamp)

    def test_failed_upgrade_rolls_back_schema_and_keeps_old_database_readable(self):
        with TemporaryDirectory() as temporary:
            database = Path(temporary) / 'index.sqlite3'
            with closing(self.legacy(database)) as db:
                db.execute('INSERT INTO scans VALUES(1,?,1,123)', (temporary,))
                db.execute("INSERT INTO folders VALUES(1,?,?,'done',NULL)", (temporary, temporary))
                db.commit()
                with patch('commonUtils._directory_schema.ensure_folder', side_effect=RuntimeError('fixture failure')):
                    with self.assertRaisesRegex(RuntimeError, 'fixture failure'):
                        upgrade_entries(db)
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
                self.assertEqual(db.execute('SELECT count(*) FROM entries').fetchone()[0], 0)
                self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='entry_nodes'").fetchone())
                self.assertTrue(database.with_suffix('.pre-v3.sqlite3').is_file())

    def test_cancelled_upgrade_does_not_change_schema_or_leave_staging_files(self):
        with TemporaryDirectory() as temporary:
            database = Path(temporary) / 'index.sqlite3'
            with closing(self.legacy(database)) as db:
                with self.assertRaises(OperationCancelled):
                    upgrade_entries(db, lambda: True)
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
                self.assertFalse(list(Path(temporary).glob('.index-upgrade-*')))

    def test_overlapping_scopes_share_records_and_changed_versions_remain_isolated(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / 'files'; child = root / 'child'; child.mkdir(parents=True)
            file = child / 'a.txt'; file.write_bytes(b'abc')
            cache = DirectoryCache(database=Path(temporary) / 'cache' / 'index.sqlite3')
            first = cache.get(root)
            scoped = cache.get(child)
            with cache._writer(lambda: False) as db:
                # Root stores a directory + file; child adds a link to the same file record.
                self.assertEqual(db.execute('SELECT count(*) FROM entry_records').fetchone()[0], 2)
                self.assertEqual(db.execute('SELECT count(*) FROM generation_entries').fetchone()[0], 3)
                self.assertEqual(db.execute('SELECT name FROM entry_nodes WHERE name=?', ('a.txt',)).fetchone()[0], 'a.txt')
                self.assertNotIn(str(root), db.execute('SELECT name FROM entry_nodes WHERE name=?', ('a.txt',)).fetchone()[0])
            file.write_bytes(b'changed')
            changed = cache.get(child)
            self.assertEqual(changed.entry(file).size, 7)
            self.assertEqual(first.entry(file).size, 3)
            self.assertEqual(scoped.entry(file).size, 3)
            with cache._writer(lambda: False) as db:
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
                parent = db.execute('SELECT parent_id FROM folder_paths WHERE path=?', (str(child),)).fetchone()[0]
                self.assertEqual(db.execute('SELECT path FROM folder_paths WHERE id=?', (parent,)).fetchone()[0], str(root))
            cache.clear()
            with cache._writer(lambda: False) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM entry_records').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT count(*) FROM entry_nodes').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT count(*) FROM folder_paths').fetchone()[0], 0)
                self.assertIsNone(cache.peek(root))
            self.assertEqual(first.entry(file).size, 3)

    def test_folder_lookup_uses_generation_parent_index_and_scoped_reads_exclude_siblings(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / 'folder9'; root.mkdir()
            for name in ('child', 'child-other'):
                folder = root / name; folder.mkdir(); (folder / 'file2.txt').write_bytes(b'a')
            cache = DirectoryCache(database=Path(temporary) / 'cache' / 'index.sqlite3')
            cache.get(root)
            scoped = cache.peek(root / 'child')
            self.assertEqual([entry.path for entry in scoped.entries], [root / 'child' / 'file2.txt'])
            self.assertEqual(scoped.entry(root / 'child-other' / 'file2.txt'), None)
            with cache._writer(lambda: False) as db:
                plan = ' '.join(row[3] for row in db.execute('EXPLAIN QUERY PLAN '
                    'SELECT path,identity FROM entries WHERE generation=? AND parent=?',
                    (scoped.entries.generation, str(root / 'child'))))
                self.assertIn('generation=? AND parent_id=?', plan)

    def test_read_only_peek_can_display_a_legacy_index_before_upgrade(self):
        with TemporaryDirectory() as temporary:
            database = Path(temporary) / 'index.sqlite3'
            root = Path(temporary) / 'files'; path = root / 'file.txt'
            with closing(self.legacy(database)) as db:
                db.execute('INSERT INTO scans VALUES(1,?,1,123)', (str(root),))
                db.execute('INSERT INTO roots VALUES(?,1,1,NULL)', (str(root),))
                db.execute("INSERT INTO folders VALUES(1,?,?,'done',NULL)", (str(root), str(root.parent)))
                db.execute('INSERT INTO entries VALUES(1,?,?,?,0,3,20,0,?,?)',
                           (str(path), str(root), path.name.casefold(), '[1, 2, 3]', _sort_key(path)))
                db.commit()
                cache = DirectoryCache(database=database)
                before = cache.peek(root)
                self.assertEqual(len(before.entries), 1)
                self.assertEqual(before.entry(path).size, 3)
                self.assertEqual(before.search_page('file')[1], 1)
                upgrade_entries(db)
                self.assertEqual(before.entry(path).size, 3)
                after = cache.peek(root)
                self.assertEqual(len(after.entries), 1)
                self.assertTrue(after.entries.compact)
                self.assertEqual(after.entry(path), before.entry(path))

    def test_schema_one_upgrade_keeps_saved_entries_and_reports_optimization(self):
        with TemporaryDirectory() as temporary:
            database = Path(temporary) / 'index.sqlite3'
            with closing(self.legacy(database)) as db:
                root = Path(temporary) / 'files'; path = root / 'file.txt'
                db.execute('PRAGMA user_version=1')
                db.execute('INSERT INTO scans VALUES(1,?,1,123)', (str(root),))
                db.execute('INSERT INTO entries VALUES(1,?,?,?,0,3,20,0,?,?)',
                           (str(path), str(root), path.name.casefold(), '[1, 2, 3]', _sort_key(path)))
                db.commit()
                messages = []
                initialize_schema(db, report=lambda done, total, message: messages.append(message))
                self.assertEqual(messages, ['Optimizing saved index'])
                self.assertEqual(db.execute('SELECT path,size FROM entries').fetchone(), (str(path), 3))
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 3)
                with closing(sqlite3.connect(database.with_suffix('.pre-v3.sqlite3'))) as backup:
                    self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 1)

    def test_deep_folder_hierarchy_is_iterative_and_interned_once(self):
        with TemporaryDirectory() as temporary:
            cache = DirectoryCache(database=Path(temporary) / 'index.sqlite3')
            with cache._writer(lambda: False) as db:
                path = Path(os.path.abspath(os.sep)) / 'depth'
                for _ in range(1100):
                    path = path / 'x'
                folder_id = ensure_folder(db, path)
                before = db.total_changes
                self.assertEqual(ensure_folder(db, path), folder_id)
                self.assertEqual(db.total_changes, before)
                self.assertEqual(db.execute('SELECT path FROM folder_paths WHERE id=?', (folder_id,)).fetchone()[0], str(path))
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
