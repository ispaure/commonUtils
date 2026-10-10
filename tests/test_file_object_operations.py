"""File operation results preserve snapshot identity and legacy boolean callers."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from commonUtils import fileUtils

class FileObjectOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.source=self.root/'source.txt'; self.source.write_text('contents')
        self.file=fileUtils.File(str(self.source))

    def test_copy_returns_new_snapshot_without_retargeting_source(self):
        target=self.root/'nested'/'copy.md'; result=self.file.copy_file(target)
        self.assertIsInstance(result,fileUtils.File); self.assertIsNot(result,self.file)
        self.assertEqual((result.path,result.file_name,result.ext,result.size),(target,'copy.md','md',8))
        self.assertEqual(self.file.path,self.source); self.assertTrue(self.source.is_file())

    def test_rename_returns_new_snapshot_and_leaves_original_metadata(self):
        target=self.root/'renamed.csv'; result=self.file.rename_file(target)
        self.assertEqual(result.path,target); self.assertEqual(result.ext,'csv')
        self.assertFalse(self.source.exists()); self.assertEqual(self.file.path,self.source)
        self.assertEqual(self.file.file_name,'source.txt')

    def test_rename_collision_raises_and_preserves_both_files(self):
        target=self.root/'existing.txt'; target.write_text('keep')
        with self.assertRaises(FileExistsError):self.file.rename_file(target)
        self.assertEqual(target.read_text(),'keep'); self.assertEqual(self.source.read_text(),'contents')
        self.assertFalse(fileUtils.rename_file(self.source,target))

    def test_force_rename_replaces_destination(self):
        target=self.root/'existing.txt'; target.write_text('old')
        self.assertEqual(self.file.rename_file(target,force=True).path,target)
        self.assertEqual(target.read_text(),'contents')

    def test_copy_errors_propagate_but_legacy_function_returns_false(self):
        with patch('commonUtils.fileUtils.copyfile',side_effect=OSError('denied')):
            with self.assertRaisesRegex(OSError,'denied'):self.file.copy_file(self.root/'copy.txt')
            self.assertFalse(fileUtils.copy_file(self.source,self.root/'copy.txt'))

    def test_move_returns_new_snapshot(self):
        target=self.root/'other'/'moved.txt'; result=self.file.move_file(target)
        self.assertEqual(result.path,target); self.assertFalse(self.source.exists())
        self.assertEqual(self.file.path,self.source)

    def test_legacy_copy_and_move_still_return_booleans(self):
        target=self.root/'copy.txt'
        self.assertIs(fileUtils.copy_file(self.source,target),True)
        self.assertIs(fileUtils.move_file(target,self.root/'moved.txt'),True)
