"""Shared typed settings tolerate bad INIs and reflect explicitly saved edits."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commonUtils.settings import get_setting, get_wheel_navigation_settings, WheelNavigationSettings


class SharedSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'settings.ini'

    def test_missing_and_malformed_files_use_defaults_without_writing(self):
        self.assertEqual(get_wheel_navigation_settings(path=self.path), WheelNavigationSettings())
        self.assertFalse(self.path.exists())
        self.path.write_text('not an INI')
        self.assertEqual(get_wheel_navigation_settings(path=self.path), WheelNavigationSettings())
        self.assertEqual(self.path.read_text(), 'not an INI')

    def test_typed_reads_and_saved_edits_are_live(self):
        self.path.write_text('[WheelNavigation]\nsensitivity=10\ncooldown_ms=100\nimmediate_notches=no\n')
        self.assertEqual(get_wheel_navigation_settings(path=self.path), WheelNavigationSettings(10, 100, False))
        self.path.write_text('[WheelNavigation]\nsensitivity=30\ncooldown_ms=400\nimmediate_notches=yes\n')
        self.assertEqual(get_wheel_navigation_settings(path=self.path), WheelNavigationSettings(30, 400, True))
        self.assertEqual(get_setting('WheelNavigation', 'sensitivity', '', path=self.path), '30')

    def test_invalid_and_nonfinite_values_fall_back_individually(self):
        for value in ('0', '-10', '101', 'nan', 'inf', 'oops'):
            with self.subTest(value=value):
                self.path.write_text(f'[WheelNavigation]\nsensitivity={value}\ncooldown_ms=100\nimmediate_notches=oops\n')
                self.assertEqual(get_wheel_navigation_settings(path=self.path), WheelNavigationSettings(20, 100, True))
        self.path.write_text('[WheelNavigation]\ncooldown_ms=-1\n')
        self.assertEqual(get_wheel_navigation_settings(path=self.path), WheelNavigationSettings())
