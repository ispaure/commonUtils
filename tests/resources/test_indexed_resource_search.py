"""Cached search never turns metadata or eligibility into access authority."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.search.indexed import IndexedLocalSearch
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.filesystem.index.reader import SqlEntries


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

    def test_local_lookup_checks_one_location_but_mapped_names_keep_both_guards(self):
        with patch.object(self.provider, '_guard', wraps=self.provider._guard) as guard:
            self.assertEqual(self.provider.entry('Straße.txt')['size'], 5)
        self.assertEqual(guard.call_count, 1)

        class Mapped(LocalFiles):
            def _physical(self, path, directory=False):
                return self.root / (path + ('.folder' if directory else '.file'))

        mapped = Mapped(self.root)
        (self.root / 'note.file').touch()
        (self.root / 'note.folder').mkdir()
        with patch.object(mapped, '_guard', wraps=mapped._guard) as guard:
            with self.assertRaisesRegex(ValueError, 'Ambiguous'):
                mapped.entry('note')
        self.assertEqual(guard.call_count, 2)

    def test_corrupt_saved_index_falls_back_to_authorized_provider_search(self):
        self.database.write_bytes(b'not a SQLite database')
        updates = []
        result = self.search.search(self.provider, '', 'STRASSE', progress=updates.append)
        self.assertTrue(result.complete)
        self.assertEqual([row['path'] for row in result.rows], ['Straße.txt'])
        self.assertEqual(updates[0].rows, result.rows)

    def prepare_many(self):
        for number in range(125):
            (self.root / f'note-{number:03}.txt').write_bytes(b'note')
        self.search.prepare(self.provider, '', cancelled=lambda: False)

    def test_cached_progress_precedes_every_hit_check_then_final_results_reconcile(self):
        self.prepare_many()
        (self.root / 'note-000.txt').unlink()
        updates = []
        entry = self.provider.entry

        def checked(path):
            self.assertTrue(updates)
            self.assertEqual(len(updates[-1].rows), 125)
            self.assertTrue(updates[-1].cached)
            return entry(path)

        with patch.object(self.provider, 'entry', side_effect=checked), \
                patch('commonUtils.search.indexed.monotonic', return_value=0):
            result = self.search.search(self.provider, '', 'note', progress=updates.append, cached_progress=True)
        self.assertEqual([len(update.rows) for update in updates], [50, 125])
        self.assertTrue(all(row['cached'] for row in updates[-1].rows))
        self.assertEqual(updates[-1].rows[0]['path'], 'note-000.txt')
        self.assertFalse(result.cached)
        self.assertEqual(len(result.rows), 124)
        self.assertTrue(all('cached' not in row for row in result.rows))

    def test_cached_display_keeps_storage_guards_and_private_admission(self):
        self.prepare_many()
        updates = []
        with patch.object(self.provider, '_guard', side_effect=[self.root, ValueError('Revoked')]):
            with self.assertRaisesRegex(ValueError, 'Revoked'):
                self.search.cached(self.provider, '', 'note', progress=updates.append)
        self.assertEqual(updates, [])
        for flag in ('private', 'session_only', 'remote_storage'):
            setattr(self.provider, flag, True)
            self.assertIsNone(self.search.cached(self.provider, '', 'note', progress=updates.append))
            setattr(self.provider, flag, False)
        self.assertEqual(updates, [])

    def test_first_saved_page_precedes_later_provider_work_and_keeps_order(self):
        from commonUtils.filesystem.index import reader
        self.prepare_many()
        publications = []
        entry = self.provider.entry
        admitted = []
        def checked(path):
            if len(admitted) == 50:
                self.assertTrue(publications, 'First page waited for later provider work')
            admitted.append(path)
            return entry(path)
        def publish(result):
            self.assertFalse(result.complete)
            publications.append(result)
            if len(publications) == 1:
                self.assertEqual(mapped.call_count, 50, 'Later SQL rows were mapped before first publication')
        with patch.object(self.provider, 'entry', side_effect=checked), \
             patch('commonUtils.search.indexed.monotonic', return_value=0), \
             patch.object(reader, '_entry', wraps=reader._entry) as mapped, \
             patch.object(SqlEntries, 'search', side_effect=AssertionError('Unbounded SQL materialization')):
            result = self.search.search(self.provider, '', 'note', progress=publish)
        self.assertEqual(len(publications[0].rows), 50)
        self.assertEqual(publications[0].rows, result.rows[:50])
        self.assertEqual([row['path'] for row in result.rows], [f'note-{n:03}.txt' for n in range(125)])
        self.assertTrue(result.complete)

    def test_cancellation_after_first_page_stops_provider_work_and_releases_snapshot(self):
        self.prepare_many()
        cancelled = False
        def publish(result):
            nonlocal cancelled
            cancelled = True
        with patch.object(self.provider, 'entry', wraps=self.provider.entry) as entry, \
                patch('commonUtils.search.indexed.monotonic', return_value=0):
            with self.assertRaises(OperationCancelled):
                self.search.search(self.provider, '', 'note', cancelled=lambda: cancelled, progress=publish)
            self.assertEqual(entry.call_count, 50)
        with self.search.cache.peek(self.root) as saved:
            self.assertTrue(saved.complete)
            self.assertEqual(saved.search_page('note', limit=1)[1], 125)

    def test_slow_validation_publishes_before_fifty_hits_and_rechecks_access(self):
        self.prepare_many()
        clock = [0.0]
        entry = self.provider.entry
        publications = []

        def checked(path):
            row = entry(path)
            clock[0] += .03  # Simulate storage latency without a timing-sensitive sleep.
            return row

        def publish(result):
            publications.append(result)
            if len(publications) == 1:
                self.assertEqual(len(result.rows), 2)
                self.assertEqual(result.scanned, 2)

        with patch('commonUtils.search.indexed.monotonic', side_effect=lambda: clock[0]), \
                patch.object(self.provider, 'entry', side_effect=checked):
            result = self.search.search(self.provider, '', 'note', progress=publish)
        self.assertEqual(len(result.rows), 125)
        self.assertEqual(publications[0].rows, result.rows[:2])

        publications.clear()
        clock[0] = 0
        guard = self.provider._guard

        def guarded(path):
            if clock[0] >= .06:
                raise ValueError('Storage changed')
            return guard(path)

        with patch('commonUtils.search.indexed.monotonic', side_effect=lambda: clock[0]), \
                patch.object(self.provider, 'entry', side_effect=checked), \
                patch.object(self.provider, '_guard', side_effect=guarded):
            with self.assertRaisesRegex(ValueError, 'Storage changed'):
                self.search.search(self.provider, '', 'note', progress=publications.append)
        self.assertEqual(publications, [])

    def test_publication_rechecks_guard_after_provider_admission(self):
        self.prepare_many()
        entry, guard = self.provider.entry, self.provider._guard
        admitted, revoked = 0, False
        publications = []
        def checked(path):
            nonlocal admitted, revoked
            row = entry(path)
            admitted += 1
            revoked = admitted == 50
            return row
        def guarded(path):
            if revoked:
                raise ValueError('Storage changed')
            return guard(path)
        with patch.object(self.provider, 'entry', side_effect=checked), \
             patch('commonUtils.search.indexed.monotonic', return_value=0), \
             patch.object(self.provider, '_guard', side_effect=guarded):
            with self.assertRaisesRegex(ValueError, 'Storage changed'):
                self.search.search(self.provider, '', 'note', progress=publications.append)
        self.assertEqual(publications, [])

    def test_saved_page_excludes_deleted_and_replaced_link_before_publication(self):
        self.prepare_many()
        (self.root / 'note-000.txt').unlink()
        linked = self.root / 'note-001.txt'
        linked.unlink()
        try:
            linked.symlink_to(self.root / 'Straße.txt')
        except OSError as error:
            self.skipTest(f'Creating a fixture symlink is unavailable: {error}')
        publications = []
        result = self.search.search(self.provider, '', 'note', progress=publications.append)
        for page in (*publications, result):
            self.assertFalse({'note-000.txt', 'note-001.txt'} & {row['path'] for row in page.rows})
        self.assertEqual(len(result.rows), 123)
        self.assertFalse(result.complete)
