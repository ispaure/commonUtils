"""Filename transformations and no-overwrite/rollback behavior on real temporary files."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
import errno
import os
import unittest
from unittest.mock import patch
from commonUtils import renameUtils as rename


class BulkRenameTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def file(self, name, content=None):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if content is not None else name)
        return path

    def test_pipeline_preserves_extension_and_unicode(self):
        path = self.file('Épisode 12.JPG')
        rules = rename.RenameRules(remove_accents=True, remove_digits=True, trim=True,
                                   replace_from='Épisode', replace_to='Chapter',
                                   prefix='Comic_', number_mode='suffix', number_padding=3,
                                   extension_mode='lower')
        self.assertEqual(rules.transform(path), 'Comic_Chapter_001.jpg')
        self.assertEqual(rename.RenameRules().transform(self.file('.hidden')), '.hidden')
        self.assertEqual(rename.RenameRules(case_mode='upper').transform(path), 'ÉPISODE 12.JPG')

    def test_regex_backreferences_literal_replacement_and_extension_opt_in(self):
        path = self.file('page_12.txt')
        rules = rename.RenameRules(regex_pattern=r'page_(\d+)', regex_replacement=r'image_\1')
        self.assertEqual(rules.transform(path), 'image_12.txt')
        self.assertEqual(replace(rules, regex_pattern=r'\.txt$', regex_replacement='.md',
                                 regex_include_extension=True).transform(path), 'page_12.md')
        self.assertEqual(rename.RenameRules(replace_from='PAGE', replace_to=r'\1',
                                           replace_case_sensitive=False).transform(path), r'\1_12.txt')
        with self.assertRaises(Exception):
            rename.plan_renames([path], replace(rules, regex_replacement=r'\2'))

    def test_removal_part_move_insert_and_name_modes(self):
        path = self.file('ABC-123-test.txt')
        rules = rename.RenameRules(remove_first=4, remove_start=3, remove_count=1,
                                   part_start=0, part_count=3, part_position=4,
                                   insert='_', insert_position=4)
        self.assertEqual(rules.transform(path), 'test_123.txt')
        self.assertEqual(rename.RenameRules(name_mode='fixed', fixed_name='New',
                                           extension_mode='fixed', extension='md').transform(path), 'New.md')
        self.assertEqual(rename.RenameRules(part_start=0, part_count=3, part_position=100,
                                           copy_part=True).transform(path), 'ABC-123-testABC.txt')

    def test_date_folder_and_natural_number_order(self):
        first = self.file('Album/page2.JPG')
        second = self.file('Album/page10.JPG')
        os.utime(first, (0, 0))
        rules = rename.RenameRules(name_mode='fixed', fixed_name='Image', date_mode='prefix',
                                   date_format='%Y', folder_mode='prefix', number_mode='suffix', number_padding=2)
        plan = rename.plan_renames([second, first], rules)
        self.assertEqual(plan.entries[0].source, first)
        self.assertEqual(plan.entries[0].target.name, f'Album_{datetime.fromtimestamp(0).year}_Image_01.JPG')
        self.assertEqual(plan.entries[1].target.name[-6:], '02.JPG')
        other = self.file('Other/page1.JPG')
        per_folder = rename.plan_renames([first, second, other], rename.RenameRules(number_mode='prefix', number_per_folder=True))
        self.assertEqual(per_folder.entries[-1].target.name, '1_page1.JPG')

    def test_conflicts_reserved_names_and_path_injection_are_rejected(self):
        a, b = self.file('a.txt'), self.file('b.txt')
        for rules in (rename.RenameRules(name_mode='fixed', fixed_name='same'),
                      rename.RenameRules(name_mode='fixed', fixed_name='CON'),
                      rename.RenameRules(prefix='../'), rename.RenameRules(prefix='bad:'),
                      rename.RenameRules(suffix='.', extension_mode='remove'), rename.RenameRules(prefix='x' * 256)):
            with self.subTest(rules=rules):
                self.assertFalse(rename.plan_renames([a, b], rules).valid)
        self.file('new_a.txt')
        plan = rename.plan_renames([a], rename.RenameRules(prefix='new_'))
        self.assertFalse(plan.valid)
        with self.assertRaises(ValueError):
            rename.apply_renames(plan)
        self.assertEqual(a.read_text(), 'a.txt')

    def test_swap_and_undo_preserve_bytes(self):
        a, b = self.file('a.txt', 'A'), self.file('b.txt', 'B')
        plan = rename.plan_renames([a, b])
        plan = replace(plan, entries=tuple(replace(entry, target=b if entry.source == a else a)
                                          for entry in plan.entries))
        result = rename.apply_renames(plan)
        self.assertTrue(result.success)
        self.assertEqual(a.read_text(), 'B')
        self.assertEqual(b.read_text(), 'A')
        undone = rename.undo_renames(result)
        self.assertTrue(undone.success)
        self.assertEqual(a.read_text(), 'A')
        self.assertEqual(b.read_text(), 'B')
        self.assertFalse(list(self.root.glob('.bulk-rename-*')))

    def test_case_only_directory_and_symlink_rename(self):
        path = self.file('IMAGE.JPG')
        plan = rename.plan_renames([path], rename.RenameRules(case_mode='lower', extension_mode='lower'))
        self.assertTrue(plan.valid)
        result = rename.apply_renames(plan)
        self.assertTrue(result.success)
        self.assertEqual((self.root / 'image.jpg').read_text(), 'IMAGE.JPG')
        folder = self.root / 'Folder.v1';folder.mkdir()
        child = folder / 'child.txt';child.write_text('untouched')
        result = rename.apply_renames(rename.plan_renames([folder], rename.RenameRules(prefix='new_')))
        self.assertTrue(result.success)
        self.assertEqual((self.root / 'new_Folder.v1/child.txt').read_text(), 'untouched')
        self.assertTrue(rename.undo_renames(result).success)
        link = self.root / 'link.txt';link.symlink_to(path.name)
        result = rename.apply_renames(rename.plan_renames([link], rename.RenameRules(prefix='new_')))
        self.assertTrue(result.success)
        self.assertEqual(os.readlink(self.root / 'new_link.txt'), path.name)

    def test_parent_and_child_selection_is_blocked(self):
        child = self.file('Folder/child.txt')
        plan = rename.plan_renames([child.parent, child], rename.RenameRules(prefix='new_'))
        self.assertFalse(plan.valid)
        self.assertIn('not both', plan.entries[1].error)

    def test_stale_source_or_destination_refuses_before_touching_files(self):
        path = self.file('a.txt')
        plan = rename.plan_renames([path], rename.RenameRules(prefix='new_'))
        path.write_text('modified')
        with self.assertRaises(RuntimeError):
            rename.apply_renames(plan)
        plan = rename.plan_renames([path], rename.RenameRules(prefix='new_'))
        self.file('new_a.txt', 'external')
        with self.assertRaises(ValueError):
            rename.apply_renames(plan)
        self.assertEqual(path.read_text(), 'modified')

    def test_cancellation_during_staging_and_publication_rolls_everything_back(self):
        a, b = self.file('a.txt'), self.file('b.txt')
        for cancel_at in (1, 3):
            progress = []
            result = rename.apply_renames(rename.plan_renames([a, b], rename.RenameRules(prefix='new_')),
                                          report=lambda done, total, message: progress.append(done),
                                          cancelled=lambda: bool(progress and progress[-1] >= cancel_at))
            self.assertTrue(result.cancelled)
            self.assertFalse(result.recovery)
            self.assertEqual(a.read_text(), 'a.txt')
            self.assertEqual(b.read_text(), 'b.txt')
            self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_publish_failure_and_racing_destination_preserve_existing_bytes(self):
        a, b = self.file('a.txt'), self.file('b.txt')
        original = rename._rename_exclusive
        def race(source, target):
            if target == self.root / 'new_b.txt':
                target.write_text('external')
            return original(source, target)
        with patch.object(rename, '_rename_exclusive', side_effect=race):
            result = rename.apply_renames(rename.plan_renames([a, b], rename.RenameRules(prefix='new_')))
        self.assertFalse(result.success)
        self.assertFalse(result.recovery)
        self.assertEqual(a.read_text(), 'a.txt')
        self.assertEqual(b.read_text(), 'b.txt')
        self.assertEqual((self.root / 'new_b.txt').read_text(), 'external')
        self.assertFalse((self.root / 'new_a.txt').exists())

    def test_failed_rollback_reports_recoverable_location_without_overwrite(self):
        path = self.file('a.txt')
        progress = []
        def report_after_stage(done, total, message):
            progress.append(done)
            if done == 1:
                path.write_text('external replacement')
        result = rename.apply_renames(rename.plan_renames([path], rename.RenameRules(prefix='new_')),
                                     report=report_after_stage, cancelled=lambda: bool(progress))
        self.assertEqual(path.read_text(), 'external replacement')
        self.assertEqual(len(result.recovery), 1)
        current, original, problem = result.recovery[0]
        self.assertEqual(current.read_text(), 'a.txt')
        self.assertEqual(original, path)

    def test_undo_refuses_edited_files_or_new_original_occupant(self):
        path = self.file('a.txt')
        result = rename.apply_renames(rename.plan_renames([path], rename.RenameRules(prefix='new_')))
        (self.root / 'new_a.txt').write_text('edited')
        with self.assertRaises(RuntimeError):
            rename.undo_renames(result)
        self.assertEqual((self.root / 'new_a.txt').read_text(), 'edited')

    def test_case_equivalent_unselected_occupant_is_a_collision(self):
        path = self.file('A.txt')
        other = self.root / 'a.txt'
        if other.exists():
            self.skipTest('Requires a case-sensitive filesystem')
        other.write_text('external')
        plan = rename.plan_renames([path], rename.RenameRules(case_mode='lower', prefix=''))
        self.assertFalse(plan.valid)
        self.assertIn('Destination already exists', plan.entries[0].error)
        self.assertEqual(path.read_text(), 'A.txt')
        self.assertEqual(other.read_text(), 'external')

    def test_successful_rename_retains_mode_and_modified_timestamp(self):
        path = self.file('a.txt')
        path.chmod(0o640)
        os.utime(path, ns=(1234567890000000000, 1234567890123456789))
        before = path.stat()
        result = rename.apply_renames(rename.plan_renames([path], rename.RenameRules(prefix='new_')))
        self.assertTrue(result.success)
        after = (self.root / 'new_a.txt').stat()
        self.assertEqual(before.st_mode, after.st_mode)
        self.assertEqual(before.st_mtime_ns, after.st_mtime_ns)

    def test_exclusive_rename_refuses_existing_empty_directory(self):
        source, target = self.root / 'source', self.root / 'target'
        source.mkdir();target.mkdir()
        with self.assertRaises(OSError) as caught:
            rename._rename_exclusive(source, target)
        self.assertEqual(caught.exception.errno, errno.EEXIST)
        self.assertTrue(source.is_dir())
        self.assertTrue(target.is_dir())

    def test_transform_uses_explicit_metadata_without_reading_disk(self):
        path = self.root / 'missing/Folder.v1'
        metadata = rename.RenameMetadata(is_directory=True, modified=datetime(2020, 1, 2))
        rules = rename.RenameRules(date_mode='prefix', date_format='%Y', extension_mode='remove')
        with patch.object(Path, 'lstat', side_effect=AssertionError('Transformation read disk')):
            self.assertEqual(rules.transform(path, metadata=metadata), '2020_Folder.v1')
            self.assertEqual(rename.RenameRules(prefix='new_').transform(path), 'new_Folder.v1')
        with self.assertRaisesRegex(ValueError, 'date is unavailable'):
            rules.transform(path)

    def test_planning_reads_source_metadata_once(self):
        path = self.file('a.txt')
        from commonUtils import renameUtils
        original = Path.lstat
        calls = []
        def tracked(path, *args, **kwargs):
            calls.append(path)
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', tracked):
            plan = renameUtils.plan_renames([path], rename.RenameRules(prefix='new_'))
        self.assertTrue(plan.valid)
        self.assertEqual(calls.count(path), 1)

    def test_single_rename_explicit_overwrite_and_failed_replacement(self):
        from commonUtils.fileUtils import rename_file
        source, target = self.file('source.txt', 'source'), self.file('target.txt', 'target')
        self.assertFalse(rename_file(source, target))
        self.assertEqual(source.read_text(), 'source')
        self.assertEqual(target.read_text(), 'target')
        with patch.object(rename.os, 'replace', side_effect=PermissionError('locked')):
            self.assertFalse(rename_file(source, target, force=True))
        self.assertEqual(target.read_text(), 'target')
        self.assertTrue(rename_file(source, target, force=True))
        self.assertEqual(target.read_text(), 'source')
        self.assertFalse(source.exists())
        self.assertTrue(rename_file(target, target))
