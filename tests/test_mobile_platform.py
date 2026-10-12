"""Simulated OS contracts; these tests do not certify mobile device support."""
import unittest
from unittest.mock import patch
from commonUtils.runtime.platform import OS, get_os, get_os_path, get_arch, Arch


class PlatformDetectionTests(unittest.TestCase):
    def test_five_platforms(self):
        for name, expected in [('win32', OS.WIN), ('darwin', OS.MAC),
                               ('linux', OS.LINUX), ('ios', OS.IOS), ('android', OS.ANDROID)]:
            with self.subTest(name=name), patch('sys.platform', name), patch('platform.system', return_value='Darwin'):
                self.assertIs(get_os(), expected)

    def test_legacy_android_is_not_linux(self):
        with patch('sys.platform', 'linux'), patch('sys.getandroidapilevel', return_value=24, create=True):
            self.assertIs(get_os(), OS.ANDROID)

    def test_legacy_ios_is_not_macos(self):
        for name in ('iOS', 'iPadOS'):
            with patch('sys.platform', 'darwin'), patch('platform.system', return_value=name):
                self.assertIs(get_os(), OS.IOS)

    def test_desktop_paths_and_unknown_contract(self):
        for name, expected in [('win32', 'w'), ('darwin', 'm'), ('linux', 'l')]:
            with patch('sys.platform', name), patch('platform.system', return_value='Darwin'):
                self.assertEqual(get_os_path('w', 'm', 'l'), expected)
        for name in ('ios', 'android', 'freebsd'):
            with patch('sys.platform', name), self.assertRaises(RuntimeError):
                get_os_path('w', 'm', 'l')
        with patch('sys.platform', 'freebsd'), self.assertRaises(RuntimeError):
            get_os()

    def test_architecture_is_independent(self):
        for name in ('arm64', 'aarch64'):
            with patch('platform.machine', return_value=name):
                self.assertIs(get_arch(), Arch.ARM_64)
