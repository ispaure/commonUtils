"""Native path spelling preserves long I/O and local storage protection."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from commonUtils.filesystem.native_paths import native_path, _extended_windows


class NativePathTests(unittest.TestCase):
    def test_windows_drive_unc_and_existing_namespaces(self):
        self.assertEqual(_extended_windows(r'C:\one\..\two'), r'\\?\C:\two')
        self.assertEqual(_extended_windows(r'\\server\share\file'), r'\\?\UNC\server\share\file')
        for value in (r'\\?\C:\two', r'\\?\UNC\server\share\file', r'\\.\pipe\name'):
            self.assertEqual(_extended_windows(value), value)

    def test_native_path_is_absolute_without_following_links(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(native_path(root / 'b').is_absolute())

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink/parent semantics')
    def test_parent_components_do_not_bypass_protection_through_a_link(self):
        from commonUtils.filesystem.local_access import protect_local_root, check_local_path
        with TemporaryDirectory() as directory:
            root = Path(directory)
            protected, public = root / 'protected', root / 'public'
            (protected / 'child').mkdir(parents=True)
            public.mkdir()
            (protected / 'secret').write_text('private fixture')
            (public / 'link').symlink_to(protected / 'child', target_is_directory=True)
            requested = public / 'link' / '..' / 'secret'
            self.assertEqual(native_path(requested).resolve(), (protected / 'secret').resolve())
            release = protect_local_root(self, protected, 'protected fixture')
            try:
                with self.assertRaises(PermissionError):
                    check_local_path(requested)
            finally:
                release()

    @unittest.skipUnless(os.name == 'nt', 'Windows filesystem acceptance')
    def test_long_publication_and_both_spellings_obey_protected_root(self):
        from commonUtils.filesystem.local_access import protect_local_root, check_local_path
        from commonUtils.filesystem.relocation import without_extended_prefix
        from commonUtils.persistence.publication import rename_exclusive
        with TemporaryDirectory() as directory:
            root = native_path(directory)
            try:
                parent = root / ('a' * 100)
                parent.mkdir()
                source, destination = parent / 'stage', parent / ('b' * 150)
                source.write_bytes(b'long-path fixture')
                self.assertGreater(len(str(destination)), 260)
                rename_exclusive(source, destination)
                self.assertEqual(destination.read_bytes(), b'long-path fixture')
                normal = Path(without_extended_prefix(str(destination)))
                release = protect_local_root(self, Path(directory), 'protected fixture')
                try:
                    for path in (normal, destination):
                        with self.assertRaises(PermissionError):
                            check_local_path(path)
                finally:
                    release()
            finally:
                shutil.rmtree(root)
