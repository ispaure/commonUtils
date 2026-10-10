"""Navigation stays local; explicit refresh scans deeper and saved branches remain usable."""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.directory_index import DirectoryCache
from commonUtils.ui.file_browser.index_policy import index_policy
from commonUtils.ui.file_browser.storage_data import collect_storage


class BrowserIndexPolicyTests(QtTestCase):
    def test_application_defaults_are_cache_first_and_legacy_defaults_unchanged(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)/'app.ini'
            self.assertFalse(index_policy(path=path).recursive_on_open)
            self.assertFalse(index_policy(path=path).refresh_cached_on_startup)
            path.write_text('[FileIndex]\nscan_on_open=false\nrecursive_on_open=true\nwatch_changes=false\n')
            policy = index_policy(path=path)
            self.assertFalse(policy.scan_on_open)
            self.assertTrue(policy.recursive_on_open)
            self.assertFalse(policy.watch_changes)
            self.assertTrue(index_policy().recursive_on_open)

    def test_visible_scan_does_not_walk_descendants_but_explicit_refresh_does(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)/'files'; nested = root/'deep'/'nested'; nested.mkdir(parents=True)
            file = nested/'data.bin'; file.write_bytes(b'abc')
            with DirectoryCache(database=Path(temporary)/'index.sqlite3') as cache:
                visible = cache.reconcile_folder(root, recursive_initial=False)
                self.assertEqual([entry.path for entry in visible.entries], [root/'deep'])
                self.assertFalse(visible.complete)
                self.assertIsNotNone(cache.peek(root))
                full = cache.reconcile_folder(root, full=True, recursive_initial=False)
                self.assertIn(file, [entry.path for entry in full.entries])
                self.assertTrue(full.complete)

    def test_empty_interrupted_root_does_not_mask_saved_ancestor(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)/'files'; child = root/'child'; child.mkdir(parents=True)
            (child/'file.bin').write_bytes(b'abc')
            with DirectoryCache(database=Path(temporary)/'index.sqlite3') as cache:
                cache.get(root)
                with closing(sqlite3.connect(cache.database)) as db, db:
                    db.execute('INSERT INTO roots VALUES(?,1,NULL,NULL)', (str(child),))
                self.assertIsNotNone(cache.peek(child))
                self.assertEqual(len(cache.peek(child).children(child)), 1)

    def test_saved_child_branch_is_visible_in_new_shallow_parent_chart(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)/'files'; child = root/'child'; child.mkdir(parents=True)
            file = child/'data.bin'; file.write_bytes(b'abc')
            with DirectoryCache(database=Path(temporary)/'index.sqlite3') as cache:
                cache.get(child)
                cache.reconcile_folder(root, recursive_initial=False)
                entries, nodes, totals, complete = collect_storage(cache, root, radial=True)
                self.assertEqual(entries, [(child, 3)])
                self.assertEqual(nodes[child], [(file, 3)])
                self.assertFalse(complete)
