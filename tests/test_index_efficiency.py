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
            cache=DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3')
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
            cache=DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3');cache.get(root)
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
            cache=DirectoryCache(database=Path(folder)/'cache'/'index.sqlite3')
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
