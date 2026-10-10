"""Discovery ordering, durable checkpoints and aggregate write amplification."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch
from commonUtils.directory_index import DirectoryCache
from commonUtils.operations import OperationCancelled
from commonUtils._directory_totals import store_folder_stats


class IndexEfficiencyTests(unittest.TestCase):
    def test_shared_parent_sort_chunks_preserve_exact_natural_order_keys(self):
        import os
        from commonUtils._directory_store import _sort_key, _encode_sort_parts
        from commonUtils.traversal import natural_path_key
        for folder in (Path('/Users/Example12/Comics'),Path('/Volumes/Drive2/Series300')):
            parts=natural_path_key(str(folder)+os.sep)
            prefix=_encode_sort_parts(parts[:-1]);tail=parts[-1]
            for name in ('Page001.cbz','002.png','Résumé12.txt','file%_2'):
                self.assertEqual(prefix+_sort_key(tail+name),_sort_key(folder/name))

    def test_resume_discovers_missing_branch_before_validating_old_files(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/'files';root.mkdir()
            old=root/'a-old';old.mkdir();(old/'file.txt').write_bytes(b'a')
            missing=root/'z-missing';missing.mkdir();(missing/'file.txt').write_bytes(b'b')
            with DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3') as cache:
                cancel=Event();scan=cache._scan_folder
                def first(*args):
                    result=scan(*args)
                    if args[4]==old:cancel.set()
                    return result
                with patch.object(cache,'_scan_folder',side_effect=first):
                    with self.assertRaises(OperationCancelled):cache.get(root,cancelled=cancel.is_set)
                (old/'file.txt').write_bytes(b'changed')
                events=[];validate=cache._validate
                def scanning(*args):events.append(('scan',args[4]));return scan(*args)
                def validating(*args,**kwargs):events.append(('validate',None));return validate(*args,**kwargs)
                with patch.object(cache,'_scan_folder',side_effect=scanning),patch.object(cache,'_validate',side_effect=validating):
                    snapshot=cache.get(root)
                self.assertEqual(events[0],('scan',missing))
                self.assertTrue(snapshot.complete)
                self.assertEqual(snapshot.folder_stats()[root].size,8)

    def test_republishing_unchanged_aggregates_does_not_rewrite_rows(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/'files';root.mkdir();(root/'file.txt').write_bytes(b'a')
            with DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3') as cache:
                cache.get(root)
                with cache._writer(lambda:False) as db:
                    generation=db.execute('SELECT completed FROM roots').fetchone()[0]
                    before=db.total_changes
                    store_folder_stats(db,generation,root)
                    self.assertEqual(db.total_changes,before)

    def test_new_subtree_reuses_completed_folders_from_partial_ancestor(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/'files';root.mkdir()
            child=root/'a-ready';child.mkdir();(child/'file.txt').write_bytes(b'abc')
            later=root/'z-later';later.mkdir();(later/'file.txt').write_bytes(b'xyz')
            with DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3') as cache:
                cancel=Event();scan=cache._scan_folder
                def scanning(*args):
                    result=scan(*args)
                    if args[4]==child:cancel.set()
                    return result
                with patch.object(cache,'_scan_folder',side_effect=scanning):
                    with self.assertRaises(OperationCancelled):cache.get(root,cancelled=cancel.is_set)
                self.assertEqual(len(cache.peek(child).entries),1)
                with patch('commonUtils.directory_index.os.scandir',side_effect=AssertionError('Completed subtree enumerated again')):
                    resumed=cache.get(child)
                self.assertTrue(resumed.complete)
                self.assertTrue(resumed.resumed)
                self.assertEqual(resumed.folder_stats()[child].size,3)
                self.assertIsNotNone(cache.status(root))

    def test_parent_imports_disjoint_child_indexes_without_reenumeration(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/'files';root.mkdir()
            children=[root/'a',root/'b']
            with DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3') as cache:
                for child in children:
                    child.mkdir();(child/'file.txt').write_bytes(b'abc');cache.get(child)
                missing=root/'missing';missing.mkdir();(missing/'new.txt').write_bytes(b'new')
                scan=cache._scan_folder; scanned=[]
                def scanning(*args):
                    scanned.append(args[4]);return scan(*args)
                with patch.object(cache,'_scan_folder',side_effect=scanning):
                    snapshot=cache.get(root)
                self.assertTrue(snapshot.complete)
                self.assertEqual(snapshot.folder_stats()[root].size,9)
                self.assertEqual(scanned,[root,missing])
                self.assertEqual(len(cache.peek(root).entries),6)

    def test_parent_prefers_specific_child_checkpoint_over_older_ancestor(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/'files';root.mkdir()
            branch=root/'branch';branch.mkdir();child=branch/'child';child.mkdir()
            old=child/'old.txt';old.write_bytes(b'old')
            with DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3') as cache:
                cache.get(branch)
                old.unlink();(child/'new.txt').write_bytes(b'newer');cache.get(child)
                scan=cache._scan_folder;scanned=[]
                def scanning(*args):scanned.append(args[4]);return scan(*args)
                with patch.object(cache,'_scan_folder',side_effect=scanning):snapshot=cache.get(root)
                self.assertTrue(snapshot.complete)
                self.assertEqual(snapshot.folder_stats()[root].size,5)
                self.assertIsNone(snapshot.entry(old))
                self.assertNotIn(child,scanned)

    def test_new_subtree_merges_specific_checkpoint_with_older_covering_ancestor(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/'files';root.mkdir()
            branch=root/'branch';branch.mkdir();child=branch/'child';child.mkdir()
            old=child/'old.txt';old.write_bytes(b'old')
            with DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3') as cache:
                cache.get(root)
                old.unlink();(child/'new.txt').write_bytes(b'newer');cache.get(child)
                scan=cache._scan_folder;scanned=[]
                def scanning(*args):scanned.append(args[4]);return scan(*args)
                with patch.object(cache,'_scan_folder',side_effect=scanning):snapshot=cache.get(branch)
                self.assertTrue(snapshot.complete)
                self.assertEqual(snapshot.folder_stats()[branch].size,5)
                self.assertIsNone(snapshot.entry(old))
                self.assertNotIn(child,scanned)

    def test_parent_drops_deleted_deep_cached_branch(self):
        import shutil
        with TemporaryDirectory() as folder:
            root=Path(folder)/'files';child=root/'intermediate'/'child';child.mkdir(parents=True)
            (child/'old.txt').write_bytes(b'old')
            with DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3') as cache:
                cache.get(child)
                shutil.rmtree(root/'intermediate')
                snapshot=cache.get(root)
                self.assertTrue(snapshot.complete)
                self.assertEqual(len(snapshot.entries),0)
                self.assertEqual(snapshot.folder_stats()[root].size,0)

    def test_navigation_reuses_fresh_ancestor_without_copying_or_validating_subtree(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/'files';child=root/'child';child.mkdir(parents=True)
            (child/'file.txt').write_bytes(b'abc')
            with DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3') as cache:
                cache.get(root)
                with patch.object(cache,'_validate',side_effect=AssertionError('Navigation validated the subtree again')):
                    snapshot=cache.get(child,reuse_for=30)
                self.assertTrue(snapshot.reused)
                self.assertEqual(snapshot.folder_stats()[child].size,3)
                self.assertEqual([entry.path for entry in snapshot.entries],[child/'file.txt'])
                with cache._writer(lambda:False) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM scans').fetchone()[0],1)
                (child/'file.txt').write_bytes(b'changed');cache.invalidate(child)
                self.assertEqual(cache.get(child,reuse_for=30).folder_stats()[child].size,7)

    def test_many_small_folders_use_bounded_batch_checkpoints(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/'files';root.mkdir()
            for i in range(40):
                child=root/str(i);child.mkdir();(child/'file.txt').write_bytes(b'x')
            with DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3') as cache:
                snapshot=cache.get(root)
                self.assertEqual(len(snapshot.entries),80)
                self.assertLess(cache.last_metrics['checkpoints'],10)
                self.assertIn('validation_seconds',cache.last_metrics)

    def test_progressive_totals_roll_up_only_changed_branches_and_match_full_pass(self):
        from commonUtils._directory_totals import collect_folder_stats
        with TemporaryDirectory() as folder:
            root=Path(folder)/'files';root.mkdir()
            for i in range(8):
                child=root/str(i);child.mkdir();(child/'file.txt').write_bytes(b'abc')
            with DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3') as cache:
                scan=cache._scan_folder
                def scanning(*args):
                    result=scan(*args)
                    cache._publish_totals(args[0],args[1],args[2],args[5]);args[0].commit()
                    return result
                with patch.object(cache,'_scan_folder',side_effect=scanning),patch('commonUtils._directory_totals.collect_folder_stats',wraps=collect_folder_stats) as full:
                    snapshot=cache.get(root)
                self.assertEqual(full.call_count,1)
                self.assertEqual(snapshot.folder_stats()[root].size,24)
                (root/'0'/'file.txt').unlink();(root/'0'/'new.cbz').write_bytes(b'changed')
                cache.invalidate(root/'0');fresh=cache.get(root)
                with cache._writer(lambda:False) as db:
                    generation=db.execute('SELECT completed FROM roots WHERE root=?',(str(root),)).fetchone()[0]
                    expected=collect_folder_stats(db,generation,root)
                actual=fresh.folder_stats()
                for path,value in expected.items():
                    self.assertEqual((actual[path].size,actual[path].files,actual[path].folders,actual[path].skipped,actual[path].extension_counts,actual[path].complete),
                                     (value.size,value.files,value.folders,value.skipped,value.extension_counts,value.complete))

    def test_fast_extension_counts_preserve_path_suffix_semantics(self):
        from collections import Counter
        from commonUtils._directory_totals import _extension
        names=['.hidden','..odd','file..CBZ','file.tar.gz','trailing.','no_extension','résumé.TXT']
        for name in names:
            self.assertEqual(_extension(str(Path('/example')/name)),Path(name).suffix.lower().lstrip('.'))
        with TemporaryDirectory() as folder:
            root=Path(folder)/'files';root.mkdir()
            for name in names:(root/name).write_bytes(b'x')
            with DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3') as cache:
                self.assertEqual(cache.get(root).folder_stats()[root].extension_counts,
                                 dict(Counter(Path(name).suffix.lower().lstrip('.') for name in names)))
