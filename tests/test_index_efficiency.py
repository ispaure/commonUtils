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
