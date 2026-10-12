"""Mobile identities are mocks; actual I/O below runs on the desktop test host."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from commonUtils.runtime.platform.capabilities import UnsupportedCapabilityError


class MobileBoundaryTests(unittest.TestCase):
    def test_desktop_entry_points_reject_mobile_before_side_effects(self):
        from commonUtils.integrations.applications import DiskApp, AppImage, Flatpak, StoreApp, open_uri
        from commonUtils.integrations.wrappers.cmdShellWrapper import exec_cmd, run_command
        from commonUtils.integrations.wrappers.cmdShellWrapper.terminal import exec_cmd_new_window
        from commonUtils.integrations.wrappers.powerShellWrapper import exec_powershell
        from commonUtils.filesystem.directories import Directory
        from commonUtils.formats.txtType import TXTFile
        from commonUtils import ui
        # Store class name is part of the established adapter API.
        actions = [lambda: DiskApp('test', '/missing').launch(),
                   lambda: AppImage('test', '/missing').launch(),
                   lambda: Flatpak('test', 'test').launch(),
                   lambda: StoreApp('test', 'test').launch(),
                   lambda: open_uri('https://example.invalid'),
                   lambda: exec_cmd('echo no'), lambda: run_command(['no']),
                   lambda: exec_cmd_new_window('no', None), lambda: exec_powershell('no'),
                   lambda: Directory(Path('.')).open(),
                   lambda: TXTFile(Path('/missing')).edit_in_default_editor(),
                   lambda: ui.display_msg_box_ok('title', 'body')]
        for mobile in ('ios', 'android'):
            with patch('sys.platform', mobile), patch('subprocess.Popen', side_effect=AssertionError('process launched')), patch('os.system', side_effect=AssertionError('shell launched')):
                for action in actions:
                    with self.subTest(platform=mobile, action=action), self.assertRaises(UnsupportedCapabilityError):
                        action()

    def test_mobile_storage_requires_host_path_and_no_desktop_migration(self):
        from tempfile import TemporaryDirectory
        from commonUtils.filesystem.storage import cache_directory, temporary_directory
        from commonUtils.configuration.layered import shared_settings, register_settings, _personal_paths
        from commonUtils.configuration.settings import settings_path
        with TemporaryDirectory() as temporary:
            for mobile in ('ios', 'android'):
                with patch('sys.platform', mobile), patch.dict(os.environ, {}, clear=True), patch.dict(_personal_paths, {}, clear=True):
                    with self.assertRaisesRegex(UnsupportedCapabilityError, 'COMMONUTILS_STORAGE_ROOT'):
                        cache_directory(create=False)
                    with self.assertRaisesRegex(UnsupportedCapabilityError, 'register a personal'):
                        shared_settings()
                    with patch.dict(os.environ, {'COMMONUTILS_STORAGE_ROOT': 'relative'}):
                        with self.assertRaises(ValueError):
                            cache_directory(create=False)
                    root = Path(temporary) / mobile
                    with patch.dict(os.environ, {'COMMONUTILS_STORAGE_ROOT': str(root)}):
                        self.assertEqual(cache_directory(create=False), root / 'Cache')
                        self.assertFalse(root.exists())
                        self.assertEqual(temporary_directory(), root / 'Temp')
                    register_settings(settings_path(), root / 'settings.ini')
                    shared_settings()
                    self.assertFalse((root / 'settings.ini').exists())

    def test_mobile_critical_logging_preserves_error_without_loading_gui(self):
        from commonUtils.runtime import diagnostics
        with patch('sys.platform', 'ios'), patch.object(diagnostics.ui, 'display_msg_box_ok') as dialog:
            with self.assertRaises(diagnostics.DebugException):
                diagnostics.log(diagnostics.Severity.CRITICAL, 'test', 'expected failure')
            dialog.assert_not_called()

    def test_legacy_android_does_not_probe_linux_mounts(self):
        from commonUtils.filesystem import network
        with patch('sys.platform', 'linux'), patch('sys.getandroidapilevel', return_value=24, create=True), patch.object(Path, 'read_text', side_effect=AssertionError('mount probe')):
            self.assertEqual(network.network_mount_roots(refresh=True), ())

    def test_clean_interpreter_portable_imports_and_document_io(self):
        script = r'''
import importlib.abc, os, sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
identity = sys.argv[1]
sys.platform = identity
if identity == 'legacy-ios':
    import platform
    sys.platform = 'darwin'
    platform.system = lambda: 'iOS'
if identity == 'legacy-android':
    sys.platform = 'linux'
    sys.getandroidapilevel = lambda: 24
class BlockDesktop(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in ('PySide6', 'pwd', 'ctypes', 'pyzipper'):
            raise AssertionError('unnecessary dependency: ' + fullname)
sys.meta_path.insert(0, BlockDesktop())
with patch('os.system', side_effect=AssertionError('import shell side effect')) as shell:
    from commonUtils.filesystem.files import File, get_split_character
    from commonUtils.filesystem.directories import Directory
    from commonUtils.formats.registry import file_from_path
    from commonUtils.formats.markdown import split_frontmatter
    from commonUtils.persistence.text import read_text_file
    from commonUtils.archives.zip_access import open_archive, copy_member_info
    from commonUtils.integrations.applications import DiskApp
    from commonUtils.runtime.platform.capabilities import UnsupportedCapabilityError
    import zipfile
    assert 'commonUtils.ui.pyside' not in sys.modules
    assert 'commonUtils.ui.native' not in sys.modules
    shell.assert_not_called()
    if identity == 'win32':
        shell.side_effect = None  # Established ANSI setup is deferred until first log call.
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / 'document.md'
        source.write_text('---\ntitle: Test\n---\n# Hello\n', encoding='utf-8')
        assert file_from_path(source).ext == 'md'
        assert split_frontmatter(source.read_text()).body == '# Hello\n'
        assert read_text_file(source) is not None
        assert len(Directory(root).list_files()) == 1
        copied = File(source).copy_file(root / 'copy.md')
        assert copied.path.read_bytes() == source.read_bytes()
        if identity in ('ios', 'android', 'legacy-android', 'legacy-ios'):
            assert get_split_character() == '/'
            assert copied.make_writable()
        for suffix in ('epub', 'cbz'):
            archive_path = root / ('book.' + suffix)
            with open_archive(archive_path, 'w') as archive:
                archive.writestr('content.txt', b'document')
            with open_archive(archive_path) as archive:
                assert archive.read('content.txt') == b'document'
                assert copy_member_info(archive.infolist()[0], archive).filename == 'content.txt'
        if identity in ('ios', 'android', 'legacy-android', 'legacy-ios'):
            try:
                import commonUtils.ui.pyside
            except UnsupportedCapabilityError:
                pass
            else:
                raise AssertionError('mobile Qt import should fail before binary initialization')
'''
        for identity in ('win32', 'darwin', 'linux', 'ios', 'android', 'legacy-android', 'legacy-ios'):
            with self.subTest(identity=identity):
                result = subprocess.run([sys.executable, '-c', script, identity], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_desktop_uri_dispatch_remains_unchanged(self):
        from commonUtils.integrations.applications import open_uri
        for identity, command in (('darwin', 'open'), ('linux', 'xdg-open')):
            with self.subTest(identity=identity), patch('sys.platform', identity), patch('platform.system', return_value='Darwin'), patch('subprocess.Popen') as launch:
                self.assertIsNone(open_uri('test:document'))
                self.assertEqual(launch.call_args.args[0], [command, 'test:document'])
        with patch('sys.platform', 'win32'), patch('os.startfile', create=True) as launch:
            self.assertIsNone(open_uri('test:document'))
            launch.assert_called_once_with('test:document')

    def test_missing_encryption_dependency_fails_without_creating_archive(self):
        from tempfile import TemporaryDirectory
        from commonUtils.archives.zip_access import open_archive
        with TemporaryDirectory() as temporary, patch.dict(sys.modules, {'pyzipper': None}):
            path = Path(temporary) / 'protected.zip'
            with self.assertRaisesRegex(RuntimeError, 'optional pyzipper'):
                with open_archive(path, 'w', password='secret'):
                    self.fail('Must not silently write an unencrypted archive')
            self.assertFalse(path.exists())

    def test_denied_write_probe_reports_error_without_success_claim(self):
        from commonUtils.runtime.platform.capabilities import CapabilityState, probe_filesystem
        with patch('commonUtils.runtime.platform.capabilities.TemporaryFile', side_effect=PermissionError('sandbox denied')):
            result = probe_filesystem(Path('.'), write=True)
        self.assertIs(result.state, CapabilityState.UNAVAILABLE)
        self.assertIn('sandbox denied', result.reason)
