"""SQLite browser admission never confuses provider replacement with local access."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from contextlib import closing
from pathlib import Path
import os
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from commonUtils.filesystem.local_access import protect_local_root
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.provider import ResourceCapabilities
from commonUtils.ui.sqlite_browser.access import check_access, provider_path

TEST_STAGE = TestStage.REGRESSION


class SQLiteAccessTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.path = self.root / 'ordinary.db'
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE items (id INTEGER PRIMARY KEY, text TEXT)')
        self.network = patch('commonUtils.filesystem.network.is_network_location', return_value=False).start()
        self.addCleanup(patch.stopall)

    def test_default_readonly_and_explicit_host_permission(self):
        self.assertEqual(check_access(self.path), self.path)
        with self.assertRaisesRegex(PermissionError, 'inspection only'):
            check_access(self.path, writable=True)
        self.assertEqual(check_access(self.path, writable=True, write_allowed=lambda path: True), self.path)
        with self.assertRaises(PermissionError):
            check_access(self.path, writable=True, write_allowed=lambda path: 1)

    def test_provider_replace_root_and_private_do_not_grant_access(self):
        fake = SimpleNamespace(root=self.root, physical_root=self.root,
                               capabilities=ResourceCapabilities(replace=True))
        with self.assertRaisesRegex(PermissionError, 'SQLite-safe'):
            provider_path(fake, self.path, writable=True)
        local = LocalFiles(self.root)
        self.assertEqual(provider_path(local, self.path), self.path)
        class MappedFiles(LocalFiles):
            pass
        with self.assertRaises(PermissionError):
            provider_path(MappedFiles(self.root), self.path)
        local.private = True
        with self.assertRaises(PermissionError):
            provider_path(local, self.path)

    def test_rechecks_protected_roots_aliases_network_and_permissions(self):
        release = protect_local_root(object(), self.root, 'Provider owns this folder')
        try:
            with self.assertRaisesRegex(PermissionError, 'Provider owns'):
                check_access(self.path)
        finally:
            release()
        alias = self.root / 'alias.db'
        alias.symlink_to(self.path)
        with self.assertRaisesRegex(PermissionError, 'linked'):
            check_access(alias)
        alias.unlink()
        os.link(self.path, alias)
        with self.assertRaisesRegex(PermissionError, 'independent'):
            check_access(self.path)
        alias.unlink()
        self.network.return_value = True
        with self.assertRaisesRegex(PermissionError, 'network'):
            check_access(self.path)
        self.network.return_value = False
        self.path.chmod(0o444)
        try:
            with self.assertRaisesRegex(PermissionError, 'writable'):
                check_access(self.path, writable=True, write_allowed=lambda path: True)
        finally:
            self.path.chmod(0o600)

    def test_explicit_managed_paths_and_renamed_schema_are_browse_only(self):
        with self.assertRaisesRegex(PermissionError, 'Managed index'):
            check_access(self.path, writable=True, write_allowed=lambda path: True,
                         readonly_paths=lambda: (self.path,))
        for names in (('jobs', 'priorities'), ('scans', 'roots', 'folder_totals', 'folder_checks')):
            candidate = self.root / f'{names[0]}.db'
            with closing(sqlite3.connect(candidate)) as db:
                for name in names:
                    db.execute(f'CREATE TABLE "{name}" (id INTEGER PRIMARY KEY)')
            self.assertEqual(check_access(candidate), candidate)
            with self.assertRaisesRegex(PermissionError, 'Managed index'):
                check_access(candidate, writable=True, write_allowed=lambda path: True)


if __name__ == '__main__':
    unittest.main()
