"""Removal never follows links or silently escalates trash failures."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from commonUtils.file_removal import removal_plan, remove_items


class RemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def file(self, name):
        path = self.root / name
        path.write_text('original')
        return path

    def test_trash_failure_leaves_files_and_children_in_place(self):
        folder = self.root / 'Folder'; folder.mkdir()
        child = folder / 'child'; child.write_text('keep')
        trash = Mock(return_value=False)
        result = remove_items(removal_plan([folder, child]), trash=trash)
        trash.assert_called_once_with(folder)
        self.assertEqual(result.completed, ())
        self.assertEqual(result.failures[0][0], folder)
        self.assertEqual(child.read_text(), 'keep')

    def test_permanent_delete_removes_link_not_target_including_dangling_link(self):
        target = self.root / 'Target'; target.mkdir()
        child = target / 'keep'; child.write_text('keep')
        link = self.root / 'Link'; link.symlink_to(target, target_is_directory=True)
        dangling = self.root / 'Missing'; dangling.symlink_to(self.root / 'absent')
        result = remove_items(removal_plan([link, dangling]), permanent=True)
        self.assertEqual(set(result.completed), {link, dangling})
        self.assertFalse(link.is_symlink())
        self.assertTrue(child.exists())

    def test_replacement_after_confirmation_is_left_untouched(self):
        path = self.file('replace.txt')
        plan = removal_plan([path])
        path.rename(self.root / 'old.txt')
        path.write_text('replacement')
        trash = Mock(return_value=True)
        result = remove_items(plan, trash=trash)
        trash.assert_not_called()
        self.assertIn('changed since confirmation', result.failures[0][1])
        self.assertEqual(path.read_text(), 'replacement')

    def test_drive_roots_rejected_and_cancel_stops_between_items(self):
        with self.assertRaises(ValueError):
            removal_plan([Path(self.root.anchor)])
        paths = [self.file('one'), self.file('two')]
        called = []
        def trash(path):
            called.append(path)
            return True
        result = remove_items(removal_plan(paths), trash=trash, cancelled=lambda: bool(called))
        self.assertTrue(result.cancelled)
        self.assertEqual(called, paths[:1])

    def test_duplicate_and_parent_selections_processed_only_once(self):
        folder = self.root / 'Folder'; folder.mkdir()
        child = folder / 'child'; child.write_text('test')
        trash = Mock(return_value=True)
        result = remove_items(removal_plan([child, folder, folder]), trash=trash)
        self.assertEqual(result.completed, (folder,))
        trash.assert_called_once_with(folder)
