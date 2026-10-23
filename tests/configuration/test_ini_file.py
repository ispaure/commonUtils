"""Generic INI parsing, format retention and conflict-safe saves."""
from configparser import Error as ConfigError
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.formats.iniType import INIFile
from commonUtils.formats.registry import file_from_path


class INIFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'config.ini'

    def test_bom_newlines_comments_case_and_literal_values_survive(self):
        self.path.write_bytes(b'\xef\xbb\xbf# note\r\n[Main]\r\nValue = 100% # literal\r\nOther:x\r\n')
        self.path.chmod(0o640)
        expected_mode = stat.S_IMODE(self.path.stat().st_mode)
        ini = INIFile(self.path).read()
        self.assertEqual(ini.get('Main', 'Value'), '100% # literal')
        self.assertIsNone(ini.get('Main', 'value'))
        ini.set('Main', 'Other', 'new')
        ini.save()
        self.assertEqual(self.path.read_bytes(), b'\xef\xbb\xbf# note\r\n[Main]\r\nValue = 100% # literal\r\nOther:new\r\n')
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), expected_mode)

    def test_add_keys_sections_and_default_inheritance(self):
        self.path.write_text('[Main]\nkey = first\n\n[Next]\nkey = second\n')
        ini = INIFile(self.path).read()
        ini.set('Main', 'added', 'value')
        ini.set('New', 'a', 'b')
        ini.set('DEFAULT', 'shared', 'yes')
        ini.save()
        loaded = INIFile(self.path).read()
        self.assertEqual(loaded.get('Main', 'added'), 'value')
        self.assertEqual(loaded.get('Next', 'shared'), 'yes')
        self.assertEqual(loaded.get('New', 'a'), 'b')

    def test_multiline_changes_preserve_comments_and_unrelated_keys(self):
        original = '[Section]\ntext = old\n    continuation\n# a note\n\nnext = unchanged\n'
        updated = INIFile.updated_text(original, {('Section', 'text'): 'new\nsecond'})
        self.assertIn('# a note\n\nnext = unchanged', updated)
        self.assertEqual(INIFile.parse(updated).get('Section', 'text'), 'new\nsecond')
        empty = INIFile.updated_text('[Section]\nkey =\nnext = x\n', {('Section', 'key'): 'value'})
        self.assertEqual(INIFile.parse(empty).get('Section', 'key'), 'value')

    def test_external_changes_are_not_overwritten(self):
        self.path.write_text('[S]\nx = old\n')
        ini = INIFile(self.path).read()
        ini.set('S', 'x', 'new')
        self.path.write_text('[S]\nx = external\n')
        with self.assertRaisesRegex(OSError, 'changed on disk'):
            ini.save()
        self.assertIn('external', self.path.read_text())

    def test_provider_boundary_blocks_existing_and_new_saves_before_parent_creation(self):
        from commonUtils.filesystem.local_access import protect_local_root
        for existing in (False, True):
            with self.subTest(existing=existing):
                path = self.path if existing else self.path.parent / 'nested/new.ini'
                if existing:
                    path.write_text('[S]\nx = old\n')
                ini = INIFile(path)
                if existing:
                    ini.read()
                ini.set('S', 'x', 'new')
                release = protect_local_root(self.id(), self.path.parent, 'Use the provider')
                try:
                    with self.assertRaisesRegex(PermissionError, 'Use the provider'):
                        ini.save()
                    if existing:
                        self.assertEqual(path.read_text(), '[S]\nx = old\n')
                    self.assertFalse((self.path.parent / 'nested').exists())
                finally:
                    release()

    def test_external_change_during_staging_preserves_file_and_loaded_baseline(self):
        import os
        self.path.write_bytes(b'[S]\nx = old\n')
        ini = INIFile(self.path).read()
        original = ini._original
        ini.set('S', 'x', 'new')
        fsync = os.fsync
        def changed_after_flush(descriptor):
            fsync(descriptor)
            self.path.write_bytes(b'[S]\nx = external\n')
        with patch('os.fsync', side_effect=changed_after_flush):
            with self.assertRaisesRegex(OSError, 'changed on disk'):
                ini.save()
        self.assertEqual(self.path.read_bytes(), b'[S]\nx = external\n')
        self.assertEqual(ini._original, original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_failed_replace_keeps_original_and_cleans_temporary_file(self):
        self.path.write_text('[S]\nx = old\n')
        ini = INIFile(self.path).read()
        ini.set('S', 'x', 'new')
        with patch('commonUtils.persistence.atomic.os.replace', side_effect=OSError('failure')):
            with self.assertRaises(OSError):
                ini.save()
        self.assertIn('old', self.path.read_text())
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_generic_values_and_registry(self):
        self.path.write_text('[S]\nx_int = not a number\n')
        ini = file_from_path(self.path)
        self.assertIsInstance(ini, INIFile)
        self.assertEqual(ini.read().get('S', 'x_int'), 'not a number')
        ini.set('S', 'x_int', 'still a string')
        ini.save()

    def test_missing_invalid_and_duplicate_files_raise(self):
        with self.assertRaises(FileNotFoundError):
            INIFile(self.path).read()
        for text in ('bad INI', '[S]\nx=1\nx=2\n'):
            self.path.write_text(text)
            with self.assertRaises(ConfigError):
                INIFile(self.path).read()


if __name__ == '__main__':
    unittest.main()
