"""Real processes share progress, serialize writers and recover saved work."""
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import monotonic, sleep
import unittest
from unittest.mock import patch

from commonUtils.filesystem.index import DirectoryCache
from commonUtils.filesystem.index.coordinator import IndexCoordinator, runner_lock, _retry_sql
from commonUtils.runtime.operations import OperationCancelled


# Each child scans an isolated fixture. A marker stops the elected owner after
# its first durable folder checkpoint, while still holding the actual writer lock.
RUNNER = r'''
import sys,time,faulthandler
from pathlib import Path
from commonUtils.filesystem.index import DirectoryCache
from commonUtils.filesystem.index.coordinator import IndexCoordinator
database, stop, marker, release, journal, trace = map(Path,sys.argv[1:])
fault = trace.open('w')
faulthandler.enable(fault)
faulthandler.dump_traceback_later(20, file=fault)
class InstrumentedCache(DirectoryCache):
    def _checkpoint(self, db, cancelled, *, force=False):
        partial = marker.name.startswith('mid') and self.active_operation.checkpoint_entries >= 512 and not marker.exists()
        super()._checkpoint(db,cancelled,force=force or partial)
        if partial:
            marker.touch()
            while not release.exists() and not cancelled(): time.sleep(.02)
    def _scan_folder(self, db, generation, root, recursive, folder, cancelled, report, **kwargs):
        with journal.open('a') as stream:
            stream.write(str(folder)+'\n')
        super()._scan_folder(db,generation,root,recursive,folder,cancelled,report,**kwargs)
        self._publish_totals(db,generation,root,cancelled)
        self._checkpoint(db,cancelled,force=True)
        report(123,0,'Saved progressive folder totals')
        if marker.name != 'unused' and not marker.exists():
            marker.touch()
            while not release.exists() and not cancelled(): time.sleep(.02)
with DirectoryCache(database=database) as cache:
    IndexCoordinator(cache).run(stop.exists,cache_factory=InstrumentedCache)
'''


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'tree'
        self.root.mkdir()
        for index in range(5):
            folder = self.root / str(index)
            folder.mkdir()
            (folder / 'file.txt').write_text('data')
        self.cache = DirectoryCache(database=self.base / 'cache' / 'index.sqlite3')
        self.addCleanup(self.cache.close)
        self.queue = IndexCoordinator(self.cache)

    def until(self, predicate, timeout=30, *, child=None):
        deadline = monotonic()+timeout
        while monotonic() < deadline:
            if child is not None and child.poll() is not None:
                _, errors = child.communicate()
                self.fail(f'Index runner exited with {child.returncode}: {errors.decode(errors="replace")}')
            # Match production follow(): short queue/schema lock contention is
            # retried while the actual index writer remains serialized.
            result = _retry_sql(predicate, cancelled=lambda: monotonic() >= deadline)
            if result:
                return result
            sleep(.03)
        try:
            with self.queue._connection() as db:
                receipts = [dict(row) for row in db.execute('SELECT state,message,error FROM jobs')]
        except sqlite3.Error as error:
            receipts = str(error)
        traces = '\n'.join(path.read_text(errors='replace') for path in self.base.glob('*.trace'))
        self.fail(f'Timed out waiting for shared index state; receipts={receipts}; child stacks={traces}')

    def runner(self, name, *, stall=False):
        stop = self.base / (name+'.stop')
        marker = self.base / (name+'.marker' if stall else 'unused')
        release = self.base / (name+'.release')
        journal = self.base / (name+'.journal')
        child = subprocess.Popen([sys.executable, '-c', RUNNER, str(self.cache.database),
                                  str(stop), str(marker), str(release), str(journal), str(self.base / (name+'.trace'))],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        def cleanup():
            stop.touch()
            try:
                child.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()
        self.addCleanup(cleanup)
        return child, stop, marker, release, journal

    def assert_done(self, identity):
        job = self.until(lambda: (job if (job := self.queue.status(identity))['state'] in ('done','error') else None))
        self.assertEqual(job['state'], 'done', job['error'])
        with self.cache.peek(self.root) as snapshot:
            self.assertTrue(snapshot.complete)
            self.assertEqual(len(snapshot.entries), 10)
        with closing(sqlite3.connect(self.cache.database)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_two_processes_share_progress_and_do_not_duplicate_scan(self):
        identity = self.queue.submit(self.root)
        first, stop, marker, release, journal = self.runner('owner', stall=True)
        self.until(marker.exists, child=first)
        second, _, _, _, other_journal = self.runner('follower')
        self.until(lambda: self.queue.status(identity)['done'] == 123)
        self.assertEqual(self.queue.submit(self.root), identity)
        self.assertEqual(self.queue.submit(self.root/'0'), identity)
        sleep(.4)
        self.assertFalse(other_journal.exists())
        release.touch()
        self.assert_done(identity)
        # A transient SQLite queue lock may yield ownership after a durable
        # checkpoint. Check the combined scan, rather than requiring one
        # process to retain ownership for the entire job on every platform.
        scanned = journal.read_text().splitlines()
        if other_journal.exists():
            scanned += other_journal.read_text().splitlines()
        self.assertCountEqual(scanned, [str(self.root), *(str(self.root / str(i)) for i in range(5))])
        self.assertIsNone(first.poll())
        self.assertIsNone(second.poll())

    def test_integrity_check_releases_database_before_fixture_cleanup(self):
        identity = self.queue.submit(self.root)
        with self.cache.get(self.root):
            pass
        self.queue._update(identity, state='done')
        connect = sqlite3.connect
        connections = []

        def tracked_connect(*args, **kwargs):
            db = connect(*args, **kwargs)
            connections.append(db)
            return db

        try:
            with patch('sqlite3.connect', side_effect=tracked_connect):
                self.assert_done(identity)
            self.assertTrue(connections)
            for db in connections:
                with self.assertRaises(sqlite3.ProgrammingError):
                    db.execute('SELECT 1')
        finally:
            for db in connections:
                db.close()

    def test_killed_owner_is_taken_over_without_resubmitting(self):
        identity = self.queue.submit(self.root)
        first, _, marker, _, journal = self.runner('owner', stall=True)
        self.until(marker.exists, child=first)
        self.runner('successor')  # This instance has no browser subscription.
        first.kill()
        first.communicate(timeout=10)
        self.assert_done(identity)
        resumed = (self.base/'successor.journal').read_text().splitlines()
        self.assertNotIn(str(self.root), resumed)  # Finished root checkpoint reused.
        self.assertEqual(len(journal.read_text().splitlines())+len(resumed), 6)

    def test_graceful_owner_exit_and_last_instance_restart(self):
        identity = self.queue.submit(self.root)
        first, stop, marker, _, _ = self.runner('owner', stall=True)
        self.until(marker.exists, child=first)
        stop.touch()
        _, errors = first.communicate(timeout=10)
        self.assertEqual(first.returncode, 0, errors.decode())
        self.assertEqual(self.queue.status(identity)['state'], 'pending')
        # All instances were closed. A fresh host resumes the durable request.
        self.runner('restarted')
        self.assert_done(identity)

    def test_crash_in_middle_of_folder_reenumerates_that_folder(self):
        for index in range(600):
            (self.root/f'file-{index}.txt').write_text('x')
        identity = self.queue.submit(self.root)
        first, _, marker, _, _ = self.runner('mid-owner', stall=True)
        self.until(marker.exists, child=first)
        first.kill()
        first.communicate(timeout=10)
        self.runner('successor')
        self.until(lambda: self.queue.status(identity)['state'] == 'done')
        with self.cache.peek(self.root) as snapshot:
            self.assertTrue(snapshot.complete)
            self.assertEqual(len(snapshot.entries), 610)
        resumed = (self.base/'successor.journal').read_text().splitlines()
        self.assertIn(str(self.root), resumed)

    def test_queued_recursive_coverage_survives_external_completion(self):
        identity = self.queue.submit(self.root)
        self.assertEqual(self.queue.submit(self.root/'0'), identity)
        with self.cache.get(self.root):
            pass
        (self.root/'0'/'later.txt').write_text('later')
        self.runner('owner')
        self.until(lambda: self.queue.status(identity)['state'] == 'done')
        with self.cache.peek(self.root) as snapshot:
            self.assertIsNotNone(snapshot.entry(self.root/'0'/'later.txt'))

    def test_detaching_follower_does_not_cancel_shared_task(self):
        identity = self.queue.submit(self.root)
        owner, _, marker, release, _ = self.runner('owner', stall=True)
        self.until(marker.exists, child=owner)
        cancelled = Event()
        def report(*args):
            cancelled.set()
        with self.assertRaises(OperationCancelled):
            self.queue.reconcile_folder(self.root, report=report, cancelled=cancelled.is_set)
        self.assertEqual(self.queue.status(identity)['state'], 'running')
        release.touch()
        self.assert_done(identity)

    def test_refresh_and_changes_during_scan_run_afterwards(self):
        identity = self.queue.submit(self.root)
        owner, _, marker, release, _ = self.runner('owner', stall=True)
        self.until(marker.exists, child=owner)
        refresh = self.queue.submit(self.root, full=True)
        changed = self.queue.submit(self.root, changes=(self.root,))
        self.assertNotEqual(identity, refresh)
        self.assertNotEqual(identity, changed)
        self.assertEqual(self.queue.submit(self.root, full=True), refresh)
        (self.root/'new.txt').write_text('new')
        release.touch()
        self.until(lambda: self.queue.status(changed)['state'] == 'done')
        with self.cache.peek(self.root) as snapshot:
            self.assertIn(self.root/'new.txt', {entry.path for entry in snapshot.entries})

    def test_shallow_parent_checks_do_not_swallow_child_or_recursive_requests(self):
        shallow = self.queue.submit(self.root, recursive_initial=False)
        self.assertNotEqual(shallow, self.queue.submit(self.root/'0', recursive_initial=False))
        self.assertNotEqual(shallow, self.queue.submit(self.root))

    def test_completed_parent_reconciliation_does_not_cover_child(self):
        with self.cache.get(self.root):
            pass
        parent = self.queue.submit(self.root)
        self.assertNotEqual(parent, self.queue.submit(self.root/'0'))

    def test_failed_job_is_terminal_and_explicit_retry_is_new(self):
        missing = self.base/'missing'
        identity = self.queue.submit(missing)
        self.runner('owner')
        self.until(lambda: self.queue.status(identity)['state'] == 'error')
        sleep(.3)
        self.assertEqual(self.queue.status(identity)['state'], 'error')
        self.assertNotEqual(identity, self.queue.submit(missing))

    def test_live_os_lock_does_not_expire_with_old_receipt(self):
        identity = self.queue.submit(self.root)
        with runner_lock(self.queue.lock_path) as owned:
            self.assertTrue(owned)
            self.queue._update(identity, state='running')
            with self.queue._connection() as db:
                db.execute('UPDATE jobs SET updated=0')
            _, _, _, _, journal = self.runner('waiting')
            sleep(.5)
            self.assertFalse(journal.exists())
        self.assert_done(identity)

    def test_simultaneous_submissions_share_one_receipt(self):
        results, errors = [], []
        def submit():
            try:
                results.append(self.queue.submit(self.root))
            except Exception as error:
                errors.append(error)
        threads = [Thread(target=submit) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertFalse(errors)
        self.assertEqual(len(set(results)), 1)

    def test_initial_schema_and_existing_library_writer_remain_serialized(self):
        self.cache.database.parent.mkdir()
        self.cache.database.touch()  # Index exists before its first schema commit.
        identity = self.queue.submit(self.root)
        with self.cache._writer(lambda: False):
            _, _, _, _, journal = self.runner('waiting')
            self.until(lambda: self.queue.status(identity)['state'] == 'running')
            sleep(.3)
            self.assertFalse(journal.exists())
        self.assert_done(identity)

    def test_short_queue_contention_retries_and_remains_cancellable(self):
        self.queue.submit(self.root)
        results = []
        with self.queue._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            thread = Thread(target=lambda: results.append(self.queue.submit(self.root/'0')))
            thread.start()
            sleep(.4)
            self.assertTrue(thread.is_alive())
        thread.join(5)
        self.assertEqual(len(results), 1)
        with self.assertRaises(OperationCancelled):
            self.queue.submit(self.root, cancelled=lambda: True)

    def test_receipt_read_does_not_require_write_lock_on_existing_schema(self):
        identity = self.queue.submit(self.root)
        with self.queue._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self.assertEqual(self.queue.status(identity)['state'], 'pending')


if __name__ == '__main__':
    unittest.main()
