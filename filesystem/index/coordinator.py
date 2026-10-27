"""Durable, process-shared browser jobs; the index itself retains its writer lock.

The queue has its own short transactions so followers never wait for an index
transaction. An OS lock elects a runner, not a PID or a heartbeat timeout. Jobs
survive the submitting browser and process; hosts opt in by running ``run``.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from time import monotonic, sleep, time
from uuid import uuid4

from ...runtime.operations import OperationCancelled, check_cancelled
from .exclusions import is_excluded, scan_exclusions


def _busy(error):
    return 'locked' in str(error) or 'busy' in str(error)


def _retry_sql(callback, cancelled=lambda: False):
    deadline = monotonic()+5
    while True:
        check_cancelled(cancelled)
        try:
            return callback()
        except sqlite3.OperationalError as error:
            if not _busy(error) or monotonic() >= deadline:
                raise
            sleep(.05)


@contextmanager
def runner_lock(path):
    """Try ownership without waiting. Never unlink a live lock's inode."""
    from ...persistence.locking import file_lock
    with file_lock(path) as acquired:
        yield acquired


class IndexCoordinator:
    def __init__(self, cache, *, notify=None, set_priority=None):
        self.cache = cache
        self.path = cache.database.with_suffix('.jobs.sqlite3')
        self.lock_path = cache.database.with_suffix('.jobs.lock')
        self.error = None
        self.participant = uuid4().hex
        self._last_priority = 0.
        self.notify = notify
        self._activity = {}
        self.set_priority = set_priority

    @staticmethod
    def _peek(cache, root):
        try:
            return cache.peek(root)
        except sqlite3.OperationalError as error:
            # The index writer may still be creating/migrating its schema. This
            # optional coverage read must not replace the cancellable writer wait.
            if not any(word in str(error) for word in ('no such table', 'locked', 'busy')):
                raise
            return None

    @contextmanager
    def _connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(self.path, timeout=.25)
        db.row_factory = sqlite3.Row
        try:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            # Existing receipt reads must not request a schema write lock. This
            # matters during Windows worker handoff and queue contention.
            if 'jobs' not in tables:
                db.execute('CREATE TABLE IF NOT EXISTS jobs ('
                       'id TEXT PRIMARY KEY, root TEXT NOT NULL, recursive INTEGER NOT NULL, '
                       'full INTEGER NOT NULL, covers_tree INTEGER NOT NULL, background INTEGER NOT NULL, '
                       'changes TEXT NOT NULL, state TEXT NOT NULL, '
                       'done INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0, '
                       "message TEXT NOT NULL DEFAULT 'Waiting for index writer', "
                       "error TEXT NOT NULL DEFAULT '', created REAL NOT NULL, updated REAL NOT NULL)")
            if 'priorities' not in tables:
                db.execute('CREATE TABLE IF NOT EXISTS priorities ('
                       'participant TEXT PRIMARY KEY, paths TEXT NOT NULL, updated REAL NOT NULL)')
            yield db
            db.commit()
        finally:
            db.close()

    def submit(self, root, *, changes=(), full=False, recursive_initial=True,
               background_priority=True, cancelled=lambda: False):
        changes = tuple(changes)
        return _retry_sql(lambda: self._submit(root, changes=changes, full=full,
                          recursive_initial=recursive_initial, background_priority=background_priority), cancelled)

    def _submit(self, root, *, changes, full, recursive_initial, background_priority):
        root = Path(root).absolute()
        recursive = full or recursive_initial
        changes = json.dumps(sorted({str(Path(path).absolute()) for path in changes}))
        covers_tree = full
        if recursive and not full:
            snapshot = self._peek(self.cache, root)
            if snapshot is None:
                covers_tree = True
            else:
                with snapshot:
                    covers_tree = not snapshot.complete
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute("SELECT * FROM jobs WHERE state IN ('pending','running') ORDER BY created").fetchall()
            for job in rows:
                source = Path(job['root'])
                # Refresh/notifications arriving during work must run afterwards:
                # they may describe a change made after that folder was scanned.
                if full or changes != '[]':
                    match = (job['state'] == 'pending' and source == root
                             and bool(job['full']) == full and job['changes'] == changes
                             and bool(job['recursive']) == recursive)
                else:
                    match = ((source == root and (job['recursive'] or not recursive))
                             or (job['covers_tree'] and source in root.parents
                                 and not is_excluded(root, scan_exclusions(source, self.cache.database))))
                if match:
                    return job['id']
            identity = uuid4().hex
            now = time()
            db.execute('INSERT INTO jobs(id,root,recursive,full,covers_tree,background,changes,state,created,updated) '
                       "VALUES(?,?,?,?,?,?,?,'pending',?,?)",
                       (identity, str(root), recursive, full, covers_tree, background_priority, changes, now, now))
            # Receipts are retained long enough for sleeping followers to catch up.
            db.execute("DELETE FROM jobs WHERE state IN ('done','error') AND updated<?", (now-7*86400,))
            return identity

    def status(self, identity):
        with self._connection() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise RuntimeError('Shared index receipt expired; refresh to retry')
            return dict(row)

    def active_job(self, root):
        """Find work a cache-only view may follow without requesting a new scan."""
        if not self.path.exists():
            return None
        root = Path(root).absolute()
        with self._connection() as db:
            for job in db.execute("SELECT * FROM jobs WHERE state IN ('pending','running') ORDER BY created"):
                source = Path(job['root'])
                if (source == root or job['covers_tree'] and source in root.parents
                        and not is_excluded(root, scan_exclusions(source, self.cache.database))):
                    return job['id']
        return None

    def reconcile_folder(self, root, *, changes=(), full=False, once=False,
                         recursive_initial=True, background_priority=True, cancelled=lambda: False,
                         report=lambda done, total, message: None):
        check_cancelled(cancelled)
        root = Path(root).absolute()
        active = self.active_job(root) if not full and not changes else None
        if active is not None:
            # A shallow active request cannot satisfy a recursive request.
            job = self.status(active)
            if job['recursive'] or not recursive_initial:
                return self.follow(active, root, cancelled=cancelled, report=report)
        if once and not full and not changes and self.cache.was_checked_this_session(root):
            snapshot = self.cache.peek(root, cancelled=cancelled)
            if snapshot is not None:
                return snapshot
        identity = self.submit(root, changes=changes, full=full, recursive_initial=recursive_initial,
                               background_priority=background_priority, cancelled=cancelled)
        return self.follow(identity, root, cancelled=cancelled, report=report)

    def follow(self, identity, root, *, cancelled=lambda: False, report=lambda done, total, message: None):
        root = Path(root).absolute()
        report(0, 0, 'Following shared index')
        while True:
            check_cancelled(cancelled)
            if self.error is not None:
                raise RuntimeError(f'Shared indexing service stopped: {self.error}')
            job = _retry_sql(lambda: self.status(identity), cancelled)
            with self.cache._state_lock:
                self.cache._shared_sources[root] = Path(job['root'])
            report(job['done'], job['total'], job['message'])
            if job['state'] == 'error':
                raise RuntimeError(job['error'])
            if job['state'] == 'done':
                with self.cache._state_lock:
                    self.cache._session_checked.add((self.cache.database, root))
                # Read the job's generation, even if an older child index exists.
                return self.cache.peek(job['root'], recursive=bool(job['recursive']), cancelled=cancelled)
            sleep(.2)

    def _update(self, identity, **values):
        values['updated'] = time()
        with self._connection() as db:
            db.execute('UPDATE jobs SET '+','.join(key+'=?' for key in values)+' WHERE id=?',
                       (*values.values(), identity))

    def run(self, cancelled, *, cache_factory=None):
        """Run off the GUI thread in every host, including hosts with no browsers.

        Stop cooperatively before host exit. Closing all hosts leaves pending work
        for the next launch. A crash releases both OS locks automatically.
        """
        try:
            self._run(cancelled, cache_factory)
        except Exception as error:
            self.error = str(error)
            raise

    def _run(self, cancelled, cache_factory):
        from .store import DirectoryCache
        cache_factory = cache_factory or DirectoryCache
        with cache_factory(database=self.cache.database) as worker:
            while not cancelled():
                if not self.path.exists():
                    sleep(.2)
                    continue
                try:
                    self._priorities(worker)
                    with runner_lock(self.lock_path) as owned:
                        if owned:
                            with self._connection() as db:
                                job = db.execute("SELECT * FROM jobs WHERE state IN ('pending','running') "
                                                 "ORDER BY CASE state WHEN 'running' THEN 0 ELSE 1 END,created LIMIT 1").fetchone()
                            if job is not None:
                                self._perform(worker, dict(job), cancelled)
                except sqlite3.OperationalError as error:
                    if not _busy(error):
                        raise
                sleep(.2)

    def _priorities(self, worker):
        now = monotonic()
        if now-self._last_priority < 1:
            return
        with self.cache._state_lock:
            paths = sorted({str(path) for group in self.cache._priority_folders.values() for path in group})
        with self._connection() as db:
            db.execute('INSERT OR REPLACE INTO priorities VALUES(?,?,?)',
                       (self.participant, json.dumps(paths), time()))
            # This freshness limit affects scheduling hints only, never ownership.
            db.execute('DELETE FROM priorities WHERE updated<?', (time()-15,))
            shared = [Path(path) for row in db.execute('SELECT paths FROM priorities') for path in json.loads(row[0])]
            activity = [dict(row) for row in db.execute(
                "SELECT * FROM jobs WHERE state IN ('pending','running') OR updated>? ORDER BY updated", (time()-60,))]
        worker.set_priority_folders('shared browsers', shared)
        current = {job['id']: (job['state'], job['updated']) for job in activity}
        if self.notify is not None:
            for job in activity:
                if self._activity.get(job['id']) != current[job['id']]:
                    job['exclusions'] = tuple(str(path) for path in scan_exclusions(Path(job['root']), self.cache.database))
                    self.notify(job)
        self._activity = current
        self._last_priority = now

    def _perform(self, worker, job, cancelled):
        identity = job['id']
        if self.set_priority is not None:
            self.set_priority(bool(job['background']))
        self._update(identity, state='running', message='Resuming shared index' if job['state'] == 'running'
                     else 'Waiting for index writer')
        last_report = 0.

        def report(done, total, message):
            nonlocal last_report
            now = monotonic()
            if now-last_report >= .2 or message == 'Saved progressive folder totals':
                self._update(identity, done=done, total=total, message=message)
                self._priorities(worker)
                last_report = now

        try:
            check_cancelled(cancelled)
            # once=False: receipts deduplicate active work. Notifications queued
            # after an earlier scan must still check the filesystem.
            full = bool(job['full'])
            if job['covers_tree']:
                # Another queued/external operation may have finished this root
                # since submission. Preserve the coverage promised to followers.
                snapshot = self._peek(worker, job['root'])
                if snapshot is not None:
                    with snapshot:
                        full |= snapshot.complete
                with worker._state_lock:
                    worker._session_checked.discard((worker.database, Path(job['root'])))
            snapshot = worker.reconcile_folder(job['root'], changes=json.loads(job['changes']),
                                              full=full, recursive_initial=bool(job['recursive']),
                                              cancelled=cancelled, report=report)
            if snapshot is not None:
                snapshot.close()
            check_cancelled(cancelled)
        except OperationCancelled:
            self._update(identity, state='pending', message='Waiting to resume saved folder checkpoints')
        except sqlite3.OperationalError as error:
            if _busy(error):
                raise  # Keep the durable receipt resumable after transient contention.
            self._update(identity, state='error', error=str(error), message='Index unavailable')
        except Exception as error:
            self._update(identity, state='error', error=str(error), message='Index unavailable')
        else:
            self._update(identity, state='done', message='Saved progressive folder totals')
