"""Filename preparation shares durable receipts without weakening metadata work."""

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
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.filesystem.index import DirectoryCache
from commonUtils.filesystem.index.coordinator import IndexCoordinator, IndexUnavailableError
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION


class SearchJobTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'files'
        for name in ('one', 'two'):
            folder = self.root / name
            folder.mkdir(parents=True)
            (folder / 'note.txt').write_text(name)
        self.cache = DirectoryCache(database=self.base / 'cache' / 'index.sqlite3')
        self.addCleanup(self.cache.close)
        self.queue = IndexCoordinator(self.cache)

    def test_pending_children_expand_to_parent_and_all_receipts_still_finish(self):
        first = self.queue.submit(self.root / 'one', names_only=True)
        second = self.queue.submit(self.root / 'two', names_only=True)
        parent = self.queue.submit(self.root, names_only=True)
        self.assertEqual(parent, first)
        self.assertEqual(self.queue.status(second)['id'], parent)
        self.assertEqual(len(self.queue.active_jobs()), 1)
        with DirectoryCache(database=self.cache.database) as worker:
            with patch.object(worker, '_scan_folder', wraps=worker._scan_folder) as scan:
                self.queue._perform(worker, self.queue._claim(), lambda: False)
            self.assertCountEqual([call.args[4] for call in scan.call_args_list],
                                  [self.root, self.root / 'one', self.root / 'two'])
        for identity in (first, second, parent):
            self.assertEqual(self.queue.status(identity)['state'], 'done')
        # Scoped publication must not expose the other joined subscriber's rows.
        with patch.object(self.queue, 'submit', return_value=second):
            with self.queue.prepare_search(self.root / 'two') as result:
                self.assertEqual(result.root, self.root / 'two')
                self.assertEqual([entry.path for entry in result.entries], [self.root / 'two' / 'note.txt'])
        self.assertFalse(self.cache.was_checked_this_session(self.root / 'two'))

    def test_running_child_cannot_be_promoted_after_claim(self):
        child = self.queue.submit(self.root / 'one', names_only=True)
        claimed = self.queue._claim()
        parent = self.queue.submit(self.root, names_only=True)
        self.assertNotEqual(child, parent)
        self.assertEqual(claimed['root'], str(self.root / 'one'))
        self.assertEqual(self.queue.status(child)['root'], claimed['root'])

    def test_excluded_pending_child_keeps_its_own_receipt(self):
        child = self.root / 'one'
        identity = self.queue.submit(child, names_only=True)
        with patch('commonUtils.filesystem.index.coordinator.scan_exclusions', return_value=(child,)):
            parent = self.queue.submit(self.root, names_only=True)
        self.assertNotEqual(identity, parent)
        self.assertEqual(len(self.queue.active_jobs()), 2)

    def test_names_only_cannot_replace_running_or_shallow_metadata_checks(self):
        with self.cache.get(self.root):
            pass
        metadata = self.queue.submit(self.root)
        claimed = self.queue._claim()
        self.assertFalse(claimed['covers_tree'])
        names = self.queue.submit(self.root, names_only=True)
        self.assertNotEqual(metadata, names)
        # A names-only job does not satisfy file metadata reconciliation either.
        self.queue._update(metadata, state='done')
        self.assertNotEqual(names, self.queue.submit(self.root))
        shallow_root = self.base / 'shallow'
        shallow_root.mkdir()
        shallow = self.queue.submit(shallow_root, recursive_initial=False)
        self.assertNotEqual(shallow, self.queue.submit(shallow_root, names_only=True))

    def test_names_only_joins_recursive_metadata_work_and_keeps_refresh_separate(self):
        parent = self.queue.submit(self.root)
        self.queue._claim()
        self.assertEqual(parent, self.queue.submit(self.root / 'one', names_only=True))
        self.assertNotEqual(parent, self.queue.submit(self.root, full=True))
        self.assertNotEqual(parent, self.queue.submit(self.root, changes=(self.root / 'one',)))

    def test_legacy_runner_and_activity_queries_never_see_filename_receipts(self):
        first = self.queue.submit(self.root / 'one', names_only=True)
        second = self.queue.submit(self.root / 'two', names_only=True)
        self.queue.submit(self.root, names_only=True)
        for state in ('pending', 'running', 'done', 'error'):
            self.queue._update(first, state=state)
            with self.queue._connection() as db:
                # These are the pre-upgrade runner, activity and pruning predicates.
                self.assertEqual(db.execute("SELECT id FROM jobs WHERE state IN ('pending','running')").fetchall(), [])
                self.assertEqual(db.execute("SELECT id FROM jobs WHERE state IN ('pending','running') OR updated>0").fetchall(), [])
                db.execute("DELETE FROM jobs WHERE state IN ('done','error') AND updated<9999999999")
            self.assertEqual(self.queue.status(first)['state'], state)
            self.assertEqual(self.queue.status(second)['state'], state)

    def test_ordinary_receipts_are_never_redirected_away_from_legacy_followers(self):
        first = self.queue.submit(self.root / 'one')
        second = self.queue.submit(self.root / 'two')
        parent = self.queue.submit(self.root, names_only=True)
        self.assertEqual(parent, first)
        self.assertFalse(self.queue.status(parent)['names_only'])
        self.assertEqual(self.queue.status(second)['id'], second)
        self.assertEqual(self.queue.status(second)['root'], str(self.root / 'two'))
        self.assertEqual(len(self.queue.active_jobs()), 2)
        with self.queue._connection() as db:
            for identity in (first, second):
                row = db.execute('SELECT state,redirect FROM jobs WHERE id=?', (identity,)).fetchone()
                self.assertEqual(tuple(row), ('pending', ''))

    def test_names_only_uses_directory_validation_and_skips_file_metadata_checks(self):
        identity = self.queue.submit(self.root, names_only=True)
        with DirectoryCache(database=self.cache.database) as worker:
            with patch.object(worker, 'get', wraps=worker.get) as get, \
                 patch.object(worker, 'reconcile_folder', side_effect=AssertionError('Visible-only reconciliation')):
                self.queue._perform(worker, self.queue._claim(), lambda: False)
            self.assertIs(get.call_args.kwargs['validate_files'], False)
        self.assertEqual(self.queue.status(identity)['state'], 'done')

    def test_receipt_and_service_failures_are_availability_errors_but_cancellation_is_distinct(self):
        with self.assertRaisesRegex(IndexUnavailableError, 'expired'):
            self.queue.status('expired')
        identity = self.queue.submit(self.root, names_only=True)
        self.queue._update(identity, state='error', error='Damaged disposable index')
        with self.assertRaisesRegex(IndexUnavailableError, 'Damaged disposable index'):
            self.queue.follow(identity, self.root)
        self.assertEqual(self.queue.status(identity)['state'], 'error')
        self.queue.error = 'Runner unavailable'
        with self.assertRaisesRegex(IndexUnavailableError, 'Runner unavailable'):
            self.queue.follow(identity, self.root)
        with self.assertRaises(OperationCancelled):
            self.queue.follow(identity, self.root, cancelled=lambda: True)

    def test_missing_completed_search_snapshot_is_an_availability_error(self):
        identity = self.queue.submit(self.root, names_only=True)
        self.queue._update(identity, state='done')
        with patch.object(self.queue, 'submit', return_value=identity):
            with self.assertRaisesRegex(IndexUnavailableError, 'snapshot unavailable'):
                self.queue.prepare_search(self.root)

    def test_host_selection_can_defer_then_choose_another_job(self):
        first = self.queue.submit(self.root / 'one', names_only=True)
        second = self.queue.submit(self.root / 'two', names_only=True)
        self.queue.select_job = lambda jobs: None
        self.assertIsNone(self.queue._claim())
        self.assertEqual(self.queue.status(first)['state'], 'pending')
        self.queue.select_job = lambda jobs: jobs[-1]
        self.assertEqual(self.queue._claim()['id'], second)
        self.assertEqual(self.queue.status(second)['state'], 'running')

    def test_yield_keeps_finished_checkpoint_and_resumes_without_reenumerating(self):
        identity = self.queue.submit(self.root, names_only=True)
        clock, yield_requested, scanned = [10.], [False], []
        self.queue.should_yield = lambda job: yield_requested[0]
        with DirectoryCache(database=self.cache.database) as worker:
            scan = worker._scan_folder
            def checked(db, generation, root, recursive, folder, cancelled, report, **kwargs):
                scanned.append(folder)
                scan(db, generation, root, recursive, folder, cancelled, report, **kwargs)
                worker._checkpoint(db, cancelled, force=True)
                if folder == self.root:
                    yield_requested[0] = True
                    clock[0] += 1
            with patch('commonUtils.filesystem.index.coordinator.monotonic', side_effect=lambda: clock[0]), \
                 patch.object(worker, '_scan_folder', side_effect=checked):
                self.queue._perform(worker, self.queue._claim(), lambda: False)
            self.assertEqual(self.queue.status(identity)['state'], 'pending')
            self.assertIn('Yielded', self.queue.status(identity)['message'])
            yield_requested[0] = False
            with patch.object(worker, '_scan_folder', side_effect=checked):
                self.queue._perform(worker, self.queue._claim(), lambda: False)
        self.assertEqual(self.queue.status(identity)['state'], 'done')
        self.assertCountEqual(scanned, [self.root, self.root / 'one', self.root / 'two'])

    def test_queue_schema_upgrade_preserves_pending_receipt_and_read_only_status(self):
        self.queue.path.parent.mkdir()
        with closing(sqlite3.connect(self.queue.path)) as db, db:
            db.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY,root TEXT NOT NULL,recursive INTEGER NOT NULL,'
                       'full INTEGER NOT NULL,covers_tree INTEGER NOT NULL,background INTEGER NOT NULL,'
                       'changes TEXT NOT NULL,state TEXT NOT NULL,done INTEGER NOT NULL DEFAULT 0,'
                       "total INTEGER NOT NULL DEFAULT 0,message TEXT NOT NULL DEFAULT '',"
                       "error TEXT NOT NULL DEFAULT '',created REAL NOT NULL,updated REAL NOT NULL)")
            db.execute("INSERT INTO jobs(id,root,recursive,full,covers_tree,background,changes,state,created,updated) "
                       "VALUES('existing',?,1,0,1,1,'[]','pending',1,1)", (str(self.root),))
        self.assertFalse(self.queue.status('existing')['names_only'])
        with self.queue._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self.assertEqual(self.queue.status('existing')['state'], 'pending')
        self.assertEqual(self.queue.submit(self.root, names_only=True), 'existing')


if __name__ == '__main__':
    unittest.main()
