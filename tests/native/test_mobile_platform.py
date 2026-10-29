"""Simulated OS contracts; these tests do not certify mobile device support."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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


class CapabilityTests(unittest.TestCase):
    def test_policy_does_not_claim_mobile_support(self):
        from commonUtils.runtime.platform.capabilities import (
            Capability, CapabilityState, capability_status, require_capability,
            UnsupportedCapabilityError, sandbox_restrictions)
        for name in ('win32', 'darwin', 'linux', 'ios', 'android'):
            with self.subTest(name=name), patch('sys.platform', name), patch('platform.system', return_value='Darwin'):
                self.assertIs(capability_status(Capability.FILESYSTEM).state, CapabilityState.UNVERIFIED)
                self.assertIs(sandbox_restrictions(), True if name in ('ios', 'android') else None)
                for capability in Capability:
                    if capability is Capability.FILESYSTEM:
                        continue
                    status = capability_status(capability)
                    self.assertIsNot(status.state, CapabilityState.VERIFIED)
                    if name in ('ios', 'android'):
                        with self.assertRaisesRegex(UnsupportedCapabilityError, 'host must provide'):
                            require_capability(capability, 'example')
                    else:
                        require_capability(capability)

    def test_path_probe_uses_real_io_and_leaves_no_files(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from commonUtils.runtime.platform.capabilities import CapabilityState, probe_filesystem
        with TemporaryDirectory() as directory:
            path = Path(directory)
            self.assertIs(probe_filesystem(path).state, CapabilityState.VERIFIED)
            self.assertIs(probe_filesystem(path, write=True).state, CapabilityState.VERIFIED)
            self.assertEqual(list(path.iterdir()), [])
            self.assertIs(probe_filesystem(path / 'missing').state, CapabilityState.UNAVAILABLE)
            with patch('pathlib.Path.open', side_effect=PermissionError('denied')):
                self.assertIn('denied', probe_filesystem(path / 'denied').reason)
