"""Sparse overrides, reset inheritance and conflict-safe software configuration."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from configparser import MissingSectionHeaderError

from commonUtils.configuration.layered import LayeredSettings, register_settings, read_values
from commonUtils.configuration.settings import get_setting


class LayeredSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.defaults = Path(self.temp.name) / 'repo.ini'
        self.personal = Path(self.temp.name) / 'appdata' / 'settings.ini'
        self.defaults.write_text('; retained\n[Options]\nsize_int = 11\nname_str = original\n', encoding='utf-8')
        self.store = register_settings(self.defaults, self.personal)

    def test_reads_do_not_create_personal_file_and_invalid_override_falls_back(self):
        original = self.defaults.read_bytes()
        self.assertEqual(get_setting('Options', 'size_int', 7, path=self.defaults), 11)
        self.assertFalse(self.personal.exists())
        self.store.save({('Options', 'size_int'): '18'})
        self.assertEqual(get_setting('Options', 'size_int', 7, path=self.defaults), 18)
        self.store.save({('Options', 'size_int'): '100'})
        self.assertEqual(get_setting('Options', 'size_int', 7, path=self.defaults, maximum=48), 11)
        self.assertEqual(self.defaults.read_bytes(), original)

    def test_reset_removes_override_and_follows_later_default_edits(self):
        self.store.save({('Options', 'name_str'): 'line one\nline two', ('Other', 'keep'): 'yes'})
        self.store.save({('Options', 'name_str'): None})
        self.assertNotIn(('Options', 'name_str'), read_values(self.personal))
        self.assertEqual(self.store.values()[('Other', 'keep')], 'yes')
        self.store.save({('Options', 'name_str'): 'new software default'}, scope='application')
        self.assertEqual(self.store.values()[('Options', 'name_str')], 'new software default')
        self.assertIn('; retained', self.defaults.read_text())

    def test_concurrent_personal_save_preserves_newer_file(self):
        self.store.save({('Options', 'size_int'): '14'})
        snapshot = self.personal.read_bytes()
        self.store.save({('Options', 'name_str'): 'newer'})
        newer = self.personal.read_bytes()
        with self.assertRaisesRegex(OSError, 'changed on disk'):
            self.store.save({('Options', 'size_int'): '20'}, expected=(snapshot,))
        self.assertEqual(self.personal.read_bytes(), newer)

    def test_software_save_preserves_bom_crlf_comments_and_unrelated_fields(self):
        self.defaults.write_bytes(b'\xef\xbb\xbf; retained\r\n[Options]\r\nsize_int = 11\r\nname_str = original\r\n')
        self.store.save({('Options', 'size_int'): '12'}, scope='application')
        self.assertEqual(self.defaults.read_bytes(), b'\xef\xbb\xbf; retained\r\n[Options]\r\nsize_int = 12\r\nname_str = original\r\n')
        self.assertFalse(self.personal.exists())

    def test_malformed_personal_file_is_not_overwritten(self):
        self.personal.parent.mkdir()
        self.personal.write_bytes(b'not an ini')
        with self.assertRaises(MissingSectionHeaderError):
            self.store.save({('Options', 'size_int'): '12'})
        self.assertEqual(self.personal.read_bytes(), b'not an ini')

    def test_paths_and_scope_cannot_collapse_defaults_into_personal(self):
        with self.assertRaises(ValueError):
            register_settings(self.defaults, self.defaults)
        with self.assertRaises(ValueError):
            LayeredSettings(self.defaults, self.personal).save({('Options', 'size_int'): None}, scope='application')

    def test_legacy_and_canonical_share_override_precedence_without_writing(self):
        from commonUtils.configuration.layered import effective_settings
        from commonUtils.configuration.legacy import config_section_map
        self.defaults.write_text('\ufeff[Options]\nMixed = default\npercent = 50%\n', encoding='utf-8')
        self.personal.parent.mkdir()
        self.personal.write_text('[Options]\nMixed = personal\n', encoding='utf-8')
        before = self.defaults.read_bytes(), self.personal.read_bytes()
        self.assertEqual(config_section_map(self.defaults, 'Options', 'mixed'), 'personal')
        self.assertEqual(config_section_map(self.defaults, 'Options', 'Mixed', case_sensitive_keys=True), 'personal')
        self.assertIsNone(config_section_map(self.defaults, 'Options', 'mixed', case_sensitive_keys=True))
        self.assertEqual(effective_settings(self.defaults)['Options']['Mixed'], 'personal')
        self.assertEqual(config_section_map(self.defaults, 'Options', 'percent'), '50%')
        self.assertEqual(before, (self.defaults.read_bytes(), self.personal.read_bytes()))
        self.personal.write_text('malformed', encoding='utf-8')
        self.assertEqual(config_section_map(self.defaults, 'Options', 'Mixed', case_sensitive_keys=True), 'default')
        self.assertEqual(self.personal.read_text(), 'malformed')

    def test_legacy_duplicate_and_bypass_policies_remain_explicit(self):
        from configparser import DuplicateOptionError, MissingSectionHeaderError
        from unittest.mock import patch
        from commonUtils.configuration.legacy import config_section_map
        self.defaults.write_text('[Options]\nName = first\nname = last\n', encoding='utf-8')
        with self.assertRaises(DuplicateOptionError):
            config_section_map(self.defaults, 'Options', 'name')
        self.assertEqual(config_section_map(self.defaults, 'Options', 'name', allow_duplicates=True), 'last')
        self.assertEqual(config_section_map(self.defaults, 'Options', 'Name', case_sensitive_keys=True), 'first')
        self.defaults.write_text('bad header\n[Options]\nname = scanned\n', encoding='utf-8')
        with self.assertRaises(MissingSectionHeaderError):
            config_section_map(self.defaults, 'Options', 'name')
        with patch('commonUtils.configuration.legacy.log'):
            self.assertEqual(config_section_map(self.defaults, 'Options', 'name', fallback_to_bypass=True), 'scanned')
        self.defaults.unlink()
        with self.assertRaises(FileNotFoundError):
            config_section_map(self.defaults, 'Options', 'name')

    def test_registration_changes_select_the_current_override_layer(self):
        from commonUtils.configuration.legacy import config_section_map
        other = Path(self.temp.name) / 'other.ini'
        other.write_text('[Options]\nsize_int = 22\n', encoding='utf-8')
        register_settings(self.defaults, other)
        self.assertEqual(config_section_map(self.defaults, 'Options', 'size_int'), '22')
        self.assertFalse(self.personal.exists())
