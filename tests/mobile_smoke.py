"""Dependency-free tests executed INSIDE CPython's mobile testbed applications.

No OS mocks, GUI, subprocesses or user documents. --target host is only a desktop
harness check and never emits a mobile success. Fixtures live in app-private temp.
"""
import argparse
import codecs
import importlib
import json
import os
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
import unittest

RESULT_PREFIX = 'COMMONUTILS_MOBILE_RESULT='
TEST_NAMES = (
    'test_runtime_identity', 'test_portable_imports', 'test_capability_boundaries',
    'test_private_storage', 'test_text_roundtrip_and_conflict',
    'test_markdown', 'test_plain_zip_containers',
)


def runtime_environment():
    if sys.platform == 'ios':
        return 'ios-simulator' if platform.ios_ver().is_simulator else 'ios-device'
    if sys.platform == 'android':
        return 'android-emulator' if platform.android_ver().is_emulator else 'android-device'
    return 'desktop-harness'


class MobileSmoke(unittest.TestCase):
    target = 'host'

    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='commonutils-smoke-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_runtime_identity(self):
        from commonUtils.runtime.platform import get_os, OS
        if self.target == 'host':
            self.assertIn(get_os(), (OS.WIN, OS.MAC, OS.LINUX))
        else:
            self.assertEqual(sys.platform, self.target)
            self.assertIs(get_os(), {'ios': OS.IOS, 'android': OS.ANDROID}[self.target])
            self.assertEqual(runtime_environment(), {'ios': 'ios-simulator', 'android': 'android-emulator'}[self.target])

    def test_portable_imports(self):
        for name in ('filesystem.files', 'filesystem.directories', 'formats.registry',
                     'formats.markdown', 'persistence.text', 'archives.zip_access'):
            importlib.import_module('commonUtils.' + name)
        self.assertNotIn('commonUtils.ui.pyside', sys.modules)
        self.assertNotIn('commonUtils.ui.native', sys.modules)
        self.assertFalse(any(name.split('.')[0] in ('PySide6', 'pyzipper') for name in sys.modules))

    def test_capability_boundaries(self):
        from commonUtils.runtime.platform.capabilities import (
            Capability, CapabilityState, capability_status, require_capability,
            UnsupportedCapabilityError, sandbox_restrictions)
        self.assertIs(capability_status(Capability.FILESYSTEM).state, CapabilityState.UNVERIFIED)
        for capability in Capability:
            if capability is Capability.FILESYSTEM:
                continue
            if self.target == 'host':
                self.assertIs(capability_status(capability).state, CapabilityState.IMPLEMENTED)
            else:
                with self.assertRaises(UnsupportedCapabilityError):
                    require_capability(capability)
        self.assertIs(sandbox_restrictions(), None if self.target == 'host' else True)
        if self.target != 'host':
            from commonUtils.integrations.applications import open_uri
            from commonUtils.integrations.wrappers.cmdShellWrapper import run_command
            with self.assertRaises(UnsupportedCapabilityError):
                open_uri('https://example.invalid')
            with self.assertRaises(UnsupportedCapabilityError):
                run_command(['must-not-run'])
            with self.assertRaises(UnsupportedCapabilityError):
                importlib.import_module('commonUtils.ui.pyside')

    def test_private_storage(self):
        from commonUtils.runtime.platform.capabilities import probe_filesystem, CapabilityState
        from commonUtils.filesystem.storage import cache_directory, temporary_workspace
        before = os.environ.get('COMMONUTILS_STORAGE_ROOT')
        os.environ['COMMONUTILS_STORAGE_ROOT'] = str(self.root / 'storage')
        try:
            self.assertFalse(cache_directory(create=False).exists())
            cache = cache_directory()
            self.assertIs(probe_filesystem(cache, write=True).state, CapabilityState.VERIFIED)
            self.assertIs(probe_filesystem(cache).state, CapabilityState.VERIFIED)
            with temporary_workspace() as folder:
                self.assertTrue(Path(folder).is_dir())
            self.assertFalse(Path(folder).exists())
        finally:
            if before is None:
                os.environ.pop('COMMONUTILS_STORAGE_ROOT', None)
            else:
                os.environ['COMMONUTILS_STORAGE_ROOT'] = before

    def test_text_roundtrip_and_conflict(self):
        from commonUtils.persistence.text import read_text_file, write_text_file, FileConflictError
        path = self.root / 'notes.md'
        original = codecs.BOM_UTF8 + 'Title\r\nCafé\r\n'.encode()
        path.write_bytes(original)
        snapshot = read_text_file(path)
        self.assertEqual(snapshot.encode(snapshot.text), original)
        edited = snapshot.encode(snapshot.text + 'Saved\n')
        write_text_file(path, edited, expected=original)
        self.assertEqual(path.read_bytes(), edited)
        with self.assertRaises(FileConflictError):
            write_text_file(path, b'stale edit', expected=original)
        self.assertEqual(path.read_bytes(), edited)

    def test_markdown(self):
        from commonUtils.formats.markdown import split_frontmatter
        from commonUtils.formats.registry import file_from_path
        from commonUtils.filesystem.directories import Directory
        path = self.root / 'document.md'
        path.write_text('---\ntitle: Mobile\n---\n# Hello\n', encoding='utf-8')
        self.assertEqual(split_frontmatter(path.read_text()).body, '# Hello\n')
        self.assertEqual(file_from_path(path).ext, 'md')
        self.assertEqual([entry.path for entry in Directory(self.root).list_files()], [path])

    def test_plain_zip_containers(self):
        from commonUtils.archives.zip_access import open_archive, validate_members, extract_archive
        for suffix in ('epub', 'cbz'):
            path = self.root / ('container.' + suffix)
            with open_archive(path, 'w') as archive:
                archive.writestr('content/document.txt', b'portable content')
            with open_archive(path) as archive:
                validate_members(archive)
                self.assertEqual(archive.read('content/document.txt'), b'portable content')
            destination = self.root / suffix
            extract_archive(path, destination)
            self.assertEqual((destination / 'content/document.txt').read_bytes(), b'portable content')
        self.assertNotIn('pyzipper', sys.modules)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('ios', 'android', 'host'), required=True)
    args = parser.parse_args(argv)
    if args.target != 'host' and sys.platform != args.target:
        parser.error(f'Expected {args.target} interpreter, got {sys.platform}; no mobile tests were run')
    if args.target == 'host' and sys.platform not in ('win32', 'darwin', 'linux'):
        parser.error('--target host is only for desktop harness validation')
    MobileSmoke.target = args.target
    suite = unittest.TestSuite(MobileSmoke(name) for name in TEST_NAMES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        'schema': 1, 'suite': 'commonUtils-mobile-smoke', 'target': args.target,
        'sys_platform': sys.platform, 'environment': runtime_environment(),
        'python': platform.python_version(), 'machine': platform.machine(),
        'tests_run': result.testsRun, 'expected_tests': list(TEST_NAMES),
        'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': len(result.skipped), 'success': result.wasSuccessful() and not result.skipped,
    }
    print(RESULT_PREFIX + json.dumps(report, sort_keys=True), flush=True)
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
