"""File operation results preserve snapshot identity and propagate I/O errors."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import os
import shutil
import stat
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from commonUtils.filesystem import files as fileUtils

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

    def test_force_rename_replaces_destination(self):
        target=self.root/'existing.txt'; target.write_text('old')
        self.assertEqual(self.file.rename_file(target,force=True).path,target)
        self.assertEqual(target.read_text(),'contents')

    def test_copy_errors_propagate(self):
        with patch('commonUtils.filesystem.files.copyfile',side_effect=OSError('denied')):
            with self.assertRaisesRegex(OSError,'denied'):self.file.copy_file(self.root/'copy.txt')

    def test_move_returns_new_snapshot(self):
        target=self.root/'other'/'moved.txt'; result=self.file.move_file(target)
        self.assertEqual(result.path,target); self.assertFalse(self.source.exists())
        self.assertEqual(self.file.path,self.source)

    def test_text_export_preserves_source_permissions_and_makes_the_destination_writable(self):
        from commonUtils.formats.txtType import TXTFile
        for existing in (False, True):
            with self.subTest(existing=existing):
                self.source.chmod(0o400)
                source_mode = stat.S_IMODE(self.source.stat().st_mode)
                target = self.root / f'export-{existing}.txt'
                if existing:
                    target.write_text('old destination')
                    target.chmod(0o400)
                document = TXTFile(self.source)
                document.line_lst = ['export', 'lines']
                document.write_lines(target)
                self.assertEqual(target.read_bytes(), 'export\nlines'.replace('\n', os.linesep).encode())
                self.assertEqual(self.source.read_text(), 'contents')
                self.assertEqual(stat.S_IMODE(self.source.stat().st_mode), source_mode)
                self.assertEqual(document.path, self.source)

    def test_text_export_protects_destination_before_creating_parents(self):
        from commonUtils.formats.txtType import TXTFile
        from commonUtils.filesystem.local_access import protect_local_root
        target = self.root / 'managed/nested/export.txt'
        protected = self.root / 'managed'
        protected.mkdir()
        document = TXTFile(self.source)
        document.line_lst = ['export']
        release = protect_local_root(self.id(), protected, 'Use the provider')
        try:
            with self.assertRaisesRegex(PermissionError, 'Use the provider'):
                document.write_lines(target)
            self.assertEqual(list(protected.iterdir()), [])
            self.assertEqual(self.source.read_text(), 'contents')
        finally:
            release()

    def test_invalid_text_encoding_does_not_truncate_output_or_change_permissions(self):
        from commonUtils.formats.txtType import TXTFile
        for alternate in (False, True):
            with self.subTest(alternate=alternate):
                target = self.root / 'export.txt' if alternate else self.source
                target.write_bytes(b'original output')
                target.chmod(0o400)
                mode = stat.S_IMODE(target.stat().st_mode)
                document = TXTFile(self.source)
                document.line_lst = ['valid prefix', '\ud800']
                with self.assertRaises(UnicodeEncodeError):
                    document.write_lines(target if alternate else None)
                self.assertEqual(target.read_bytes(), b'original output')
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), mode)

    def test_executable_permissions_use_literal_arguments_instead_of_a_shell(self):
        from commonUtils.integrations.wrappers import cmdShellWrapper
        result = cmdShellWrapper.CommandResult(0)
        with patch.object(cmdShellWrapper, 'run_command', return_value=result) as run:
            self.file.set_executable_permission()
        run.assert_called_once_with(['chmod', '+x', str(self.source.absolute())],
                                    idle_timeout=15, shell=False)

    def test_relative_option_like_executable_name_becomes_an_absolute_operand(self):
        from commonUtils.integrations.wrappers import cmdShellWrapper
        relative = Path('-R')
        with patch.object(cmdShellWrapper, 'run_command', return_value=cmdShellWrapper.CommandResult(0)) as run:
            fileUtils.File(relative).set_executable_permission()
        self.assertEqual(run.call_args.args[0], ['chmod', '+x', str(relative.absolute())])
        self.assertFalse(run.call_args.kwargs['shell'])

    def test_executable_permission_failure_is_not_silently_ignored(self):
        from commonUtils.integrations.wrappers import cmdShellWrapper
        result = cmdShellWrapper.CommandResult(3, stderr=('permission denied',))
        with patch.object(cmdShellWrapper, 'run_command', return_value=result):
            with self.assertRaises(OSError):
                self.file.set_executable_permission()

    @unittest.skipUnless(os.name != 'nt' and shutil.which('chmod'), 'Native POSIX chmod required')
    def test_executable_permissions_preserve_literal_shell_metacharacters_in_filename(self):
        path = self.root / 'literal "quotes" $(printf substituted)'
        path.write_bytes(b'fixture payload')
        path.chmod(0o600)
        before = stat.S_IMODE(path.stat().st_mode)
        fileUtils.File(path).set_executable_permission()
        after = stat.S_IMODE(path.stat().st_mode)
        self.assertTrue(after & stat.S_IXUSR)
        self.assertEqual(after & ~0o111, before & ~0o111)
        self.assertEqual(path.read_bytes(), b'fixture payload')
