"""Cached search never turns metadata or eligibility into access authority."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.search.indexed import IndexedLocalSearch
from commonUtils.runtime.resources.local import LocalFiles


class IndexedSearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.root = base / 'files'
        self.root.mkdir()
        (self.root / 'Straße.txt').write_bytes(b'hello')
        self.database = base / 'index.sqlite3'
        self.provider = LocalFiles(self.root)
        self.search = IndexedLocalSearch(self.database, eligible=lambda provider: True)
        self.addCleanup(self.search.cache.close)

    def test_private_and_session_providers_stay_in_ram_despite_admission(self):
        for flag in ('private', 'session_only', 'remote_storage'):
            with self.subTest(flag=flag):
                setattr(self.provider, flag, True)
                self.search.prepare(self.provider, '', cancelled=lambda: False)
                result = self.search.search(self.provider, '', 'STRASSE')
                self.assertEqual(len(result.rows), 1)
                self.assertFalse(self.database.exists())
                setattr(self.provider, flag, False)

    def test_cached_rows_revalidate_access_and_missing_files(self):
        self.search.prepare(self.provider, '', cancelled=lambda: False)
        with patch.object(self.provider, 'entry', side_effect=ValueError('revoked')):
            result = self.search.search(self.provider, '', 'STRASSE')
            self.assertEqual(result.rows, [])
            self.assertFalse(result.complete)
            self.assertEqual(len(result.errors), 1)
        (self.root / 'Straße.txt').unlink()
        result = self.search.search(self.provider, '', 'STRASSE')
        self.assertEqual(result.rows, [])
