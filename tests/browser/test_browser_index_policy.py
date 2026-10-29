"""Navigation stays local; explicit refresh scans deeper and saved branches remain usable."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.filesystem.index import DirectoryCache
from commonUtils.ui.file_browser.index_policy import index_policy
from commonUtils.ui.file_browser.storage_data import collect_storage


class BrowserIndexPolicyTests(QtTestCase):
    def test_shared_scan_views_follow_the_same_source_without_marking_early_completion(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).absolute()
            parent, child, descendant = root / 'parent', root / 'parent/child', root / 'parent/child/nested'
            with DirectoryCache(database=root / 'index.sqlite3') as cache:
                self.assertEqual(cache.shared_source(child), child)
                cache.follow_shared_source(child, parent)
                cache.follow_shared_source(descendant, child)
                self.assertEqual(cache.shared_source(descendant), parent)
                self.assertFalse(cache.was_checked_this_session(child))
                cache.shared_scan_completed(child, parent)
                self.assertTrue(cache.was_checked_this_session(child))
                self.assertFalse(cache.was_checked_this_session(descendant))
                self.assertEqual(cache.shared_source(child), parent)
                self.assertFalse(cache.database.exists())

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

    def test_shallow_browser_totals_reuse_saved_children_and_parent(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)/'files'; child = root/'child'; child.mkdir(parents=True)
            (child/'data.bin').write_bytes(b'abc')
            with DirectoryCache(database=Path(temporary)/'index.sqlite3') as cache:
                cache.get(child)
                visible = cache.reconcile_folder(root, recursive_initial=False)
                totals = visible.folder_stats(children_of=root)
                self.assertEqual(totals[child].size, 3)
                self.assertTrue(totals[child].stale)
                # A recursively saved parent also supplies child totals after a
                # local-only startup check, without rewalking its descendants.
                cache.get(root)
                visible = cache.reconcile_folder(root, recursive_initial=False)
                self.assertEqual(visible.folder_stats(children_of=root)[child].size, 3)

    def test_shallow_child_uses_ancestor_cache_but_full_refresh_can_reduce_sizes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)/'files'; parent = root/'parent'; child = parent/'child'
            child.mkdir(parents=True); file = child/'data.bin'; file.write_bytes(b'abc')
            with DirectoryCache(database=Path(temporary)/'index.sqlite3') as cache:
                cache.get(root)
                visible = cache.reconcile_folder(parent, recursive_initial=False)
                self.assertEqual(visible.folder_stats(children_of=parent)[child].size, 3)
                file.unlink()
                refreshed = cache.reconcile_folder(parent, full=True)
                self.assertEqual(refreshed.folder_stats(children_of=parent)[child].size, 0)
                child.rmdir()
                visible = cache.reconcile_folder(parent, recursive_initial=False)
                self.assertNotIn(child, visible.folder_stats(children_of=parent))
