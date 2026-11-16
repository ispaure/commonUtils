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

_ACTIVE_STATES = "('pending','running','pending_names','running_names')"


class IndexUnavailableError(OSError):
    """The disposable shared index cannot supply the requested snapshot."""


def _job(row):
    """Keep new filename receipts invisible to older runners and observers."""
    value = dict(row)
    if value['names_only']:
        if value['state'].endswith('_names'):
            value['state'] = value['state'][:-6]
        value['updated'] = value['names_updated']
    return value


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
    def __init__(self, cache, *, notify=None, set_priority=None, select_job=None, should_yield=None):
        self.cache = cache
        self.path = cache.database.with_suffix('.jobs.sqlite3')
        self.lock_path = cache.database.with_suffix('.jobs.lock')
        self.error = None
        self.participant = uuid4().hex
        self._last_priority = 0.
        self.notify = notify
        self._activity = {}
        self.set_priority = set_priority
        self.select_job = select_job
        self.should_yield = should_yield

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
                       "error TEXT NOT NULL DEFAULT '', created REAL NOT NULL, updated REAL NOT NULL, "
                       "names_only INTEGER NOT NULL DEFAULT 0, redirect TEXT NOT NULL DEFAULT '', "
                       "names_updated REAL NOT NULL DEFAULT 0)")
            if 'priorities' not in tables:
                db.execute('CREATE TABLE IF NOT EXISTS priorities ('
                       'participant TEXT PRIMARY KEY, paths TEXT NOT NULL, updated REAL NOT NULL)')
            columns = {row[1] for row in db.execute('PRAGMA table_info(jobs)')}
            if not {'names_only', 'redirect', 'names_updated'} <= columns:
                # Serialize upgrades, then re-read after another process's
                # migration. Existing receipt reads remain read-only afterward.
                db.execute('BEGIN IMMEDIATE')
                columns = {row[1] for row in db.execute('PRAGMA table_info(jobs)')}
                if 'names_only' not in columns:
                    db.execute('ALTER TABLE jobs ADD COLUMN names_only INTEGER NOT NULL DEFAULT 0')
                if 'redirect' not in columns:
                    db.execute("ALTER TABLE jobs ADD COLUMN redirect TEXT NOT NULL DEFAULT ''")
                if 'names_updated' not in columns:
                    db.execute('ALTER TABLE jobs ADD COLUMN names_updated REAL NOT NULL DEFAULT 0')
                    db.execute("UPDATE jobs SET names_updated=updated,updated=0,state=state||'_names' "
                               "WHERE names_only=1 AND state IN ('pending','running','done','error','joined')")
                db.commit()
            yield db
            db.commit()
        finally:
            db.close()

    def submit(self, root, *, changes=(), full=False, recursive_initial=True,
               background_priority=True, names_only=False, cancelled=lambda: False):
        changes = tuple(changes)
        if names_only and (full or changes or not recursive_initial):
            raise ValueError('Names-only preparation requires a recursive request without explicit changes or refresh')
        return _retry_sql(lambda: self._submit(root, changes=changes, full=full,
                          recursive_initial=recursive_initial, background_priority=background_priority,
                          names_only=names_only), cancelled)

    def _submit(self, root, *, changes, full, recursive_initial, background_priority, names_only):
        root = Path(root).absolute()
        recursive = full or recursive_initial
        changes = json.dumps(sorted({str(Path(path).absolute()) for path in changes}))
        covers_tree = full or names_only
        if recursive and not covers_tree:
            snapshot = self._peek(self.cache, root)
            if snapshot is None:
                covers_tree = True
            else:
                with snapshot:
                    covers_tree = not snapshot.complete
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = [_job(row) for row in db.execute(f'SELECT * FROM jobs WHERE state IN {_ACTIVE_STATES} ORDER BY created')]
            for job in rows:
                source = Path(job['root'])
                # Refresh/notifications arriving during work must run afterwards:
                # they may describe a change made after that folder was scanned.
                if full or changes != '[]':
                    match = (job['state'] == 'pending' and source == root
                             and bool(job['full']) == full and job['changes'] == changes
                             and bool(job['recursive']) == recursive)
                else:
                    # Names-only validation covers a recursive search scope,
                    # but cannot stand in for ordinary file-metadata checks.
                    compatible = bool(job['covers_tree']) if names_only else not job['names_only']
                    match = compatible and (
                        (source == root and (job['recursive'] or not recursive))
                        or (job['covers_tree'] and source in root.parents
                            and not is_excluded(root, scan_exclusions(source, self.cache.database))))
                if match:
                    if not background_priority and job['background']:
                        self._write(db, job['id'], names_only=job['names_only'], background=0)
                    return job['id']
            # A pending child has no in-flight traversal to retarget. Expand its
            # receipt to a covering ancestor and redirect other compatible
            # pending children, retaining every existing follower identity.
            if covers_tree and not full and changes == '[]':
                exclusions = scan_exclusions(root, self.cache.database)
                children = [job for job in rows if job['state'] == 'pending'
                            and job['recursive'] and not job['full'] and job['changes'] == '[]'
                            and (Path(job['root']) == root or root in Path(job['root']).parents)
                            and not is_excluded(Path(job['root']), exclusions)]
                if children:
                    ordinary = [job for job in children if not job['names_only']]
                    leader = (ordinary or children)[0]['id']
                    # An ordinary metadata request upgrades the combined job;
                    # this preserves that subscriber's stronger validation.
                    names = names_only and not ordinary
                    background = background_priority and all(job['background'] for job in children)
                    self._write(db, leader, names_only=names, root=str(root), recursive=1,
                                covers_tree=1, background=background, state='pending')
                    for child in children:
                        # Older callers cannot resolve a redirected ordinary
                        # receipt. Only filename receipts may become aliases.
                        if child['id'] != leader and child['names_only']:
                            self._write(db, child['id'], names_only=True, state='joined', redirect=leader)
                    return leader
            identity = uuid4().hex
            now = time()
            db.execute('INSERT INTO jobs(id,root,recursive,full,covers_tree,background,changes,state,created,updated,names_only,names_updated) '
                       'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (identity, str(root), recursive, full, covers_tree, background_priority, changes,
                        'pending_names' if names_only else 'pending', now, 0 if names_only else now,
                        names_only, now if names_only else 0))
            # Receipts are retained long enough for sleeping followers to catch up.
            db.execute("DELETE FROM jobs WHERE (state IN ('done','error') AND updated<?) "
                       "OR (state IN ('done_names','error_names') AND names_updated<?)", (now-7*86400, now-7*86400))
            while db.execute("DELETE FROM jobs WHERE state='joined_names' AND redirect NOT IN (SELECT id FROM jobs)").rowcount:
                pass
            return identity

    def status(self, identity):
        with self._connection() as db:
            visited = set()
            while identity not in visited:
                visited.add(identity)
                row = db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone()
                if row is None:
                    raise IndexUnavailableError('Shared index receipt expired; refresh to retry')
                if row['state'] != 'joined_names':
                    return _job(row)
                identity = row['redirect']
            raise IndexUnavailableError('Invalid shared index receipt redirect')

    def active_jobs(self):
        """Read canonical pending/running receipts for host scheduling policy."""
        if not self.path.exists():
            return []
        with self._connection() as db:
            return [_job(row) for row in db.execute(f'SELECT * FROM jobs WHERE state IN {_ACTIVE_STATES} '
                                                  "ORDER BY CASE WHEN state IN ('running','running_names') THEN 0 ELSE 1 END,created")]

    def active_job(self, root):
        """Find work a cache-only view may follow without requesting a new scan."""
        if not self.path.exists():
            return None
        root = Path(root).absolute()
        with self._connection() as db:
            for job in db.execute(f'SELECT * FROM jobs WHERE state IN {_ACTIVE_STATES} ORDER BY created'):
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
            if not job['names_only'] and (job['recursive'] or not recursive_initial):
                return self.follow(active, root, cancelled=cancelled, report=report)
        if once and not full and not changes and self.cache.was_checked_this_session(root):
            snapshot = self.cache.peek(root, cancelled=cancelled)
            if snapshot is not None:
                return snapshot
        identity = self.submit(root, changes=changes, full=full, recursive_initial=recursive_initial,
                               background_priority=background_priority, cancelled=cancelled)
        return self.follow(identity, root, cancelled=cancelled, report=report)

    def prepare_search(self, root, *, cancelled=lambda: False, report=lambda done, total, message: None):
        """Coalesce recursive filename validation and return the requested scope.

        Cancelling this follower never cancels the host-owned traversal. Provider
        admission and publication checks remain the application's responsibility.
        """
        identity = self.submit(root, names_only=True, background_priority=False, cancelled=cancelled)
        snapshot = self.follow(identity, root, cancelled=cancelled, report=report)
        if snapshot is not None:
            snapshot.close()
        snapshot = self.cache.peek(root, cancelled=cancelled)
        if snapshot is None:
            raise IndexUnavailableError('Shared index snapshot unavailable; refresh to retry')
        return snapshot

    def follow(self, identity, root, *, cancelled=lambda: False, report=lambda done, total, message: None):
        root = Path(root).absolute()
        report(0, 0, 'Following shared index')
        while True:
            check_cancelled(cancelled)
            if self.error is not None:
                raise IndexUnavailableError(f'Shared indexing service stopped: {self.error}')
            job = _retry_sql(lambda: self.status(identity), cancelled)
            with self.cache._state_lock:
                self.cache._shared_sources[root] = Path(job['root'])
            report(job['done'], job['total'], job['message'])
            if job['state'] == 'error':
                raise IndexUnavailableError(job['error'])
            if job['state'] == 'done':
                if not job['names_only']:
                    with self.cache._state_lock:
                        self.cache._session_checked.add((self.cache.database, root))
                # Read the job's generation, even if an older child index exists.
                return self.cache.peek(job['root'], recursive=bool(job['recursive']), cancelled=cancelled)
            sleep(.2)

    def _update(self, identity, **values):
        with self._connection() as db:
            row = db.execute('SELECT names_only FROM jobs WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise IndexUnavailableError('Shared index receipt expired; refresh to retry')
            self._write(db, identity, names_only=row['names_only'], **values)

    @staticmethod
    def _write(db, identity, *, names_only, **values):
        stamp = time()
        values.update(names_only=names_only, updated=0 if names_only else stamp,
                      names_updated=stamp if names_only else 0)
        if names_only and 'state' in values:
            values['state'] += '_names'
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
                            job = self._claim()
                            if job is not None:
                                self._perform(worker, job, cancelled)
                except sqlite3.OperationalError as error:
                    if not _busy(error):
                        raise
                sleep(.2)

    def _claim(self):
        # Claim in the same short queue transaction as selection, so a later
        # ancestor submission cannot promote a receipt already chosen to run.
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            jobs = [_job(row) for row in db.execute(f'SELECT * FROM jobs WHERE state IN {_ACTIVE_STATES} '
                                                  "ORDER BY CASE WHEN state IN ('running','running_names') THEN 0 ELSE 1 END,created")]
            if not jobs:
                return None
            selected = self.select_job(jobs) if self.select_job is not None else jobs[0]
            if selected is None:
                return None
            job = next((job for job in jobs if job['id'] == selected['id']), None)
            if job is None:
                raise ValueError('Index job selection must return an active receipt')
            self._write(db, job['id'], names_only=job['names_only'], state='running')
            return job

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
            activity = [_job(row) for row in db.execute(
                f"SELECT * FROM jobs WHERE state!='joined_names' AND (state IN {_ACTIVE_STATES} OR max(updated,names_updated)>?) "
                "ORDER BY max(updated,names_updated)", (time()-60,))]
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
        next_yield_check = 0.
        yielded = False

        def interrupted():
            nonlocal next_yield_check, yielded
            if cancelled() or yielded:
                return True
            now = monotonic()
            if self.should_yield is not None and now >= next_yield_check:
                next_yield_check = now + .2
                yielded = bool(self.should_yield(job))
            return yielded

        def report(done, total, message):
            nonlocal last_report
            now = monotonic()
            if now-last_report >= .2 or message == 'Saved progressive folder totals':
                self._update(identity, done=done, total=total, message=message)
                self._priorities(worker)
                last_report = now

        try:
            check_cancelled(interrupted)
            # once=False: receipts deduplicate active work. Notifications queued
            # after an earlier scan must still check the filesystem.
            full = bool(job['full'])
            if job['covers_tree'] and not job['names_only']:
                # Another queued/external operation may have finished this root
                # since submission. Preserve the coverage promised to followers.
                snapshot = self._peek(worker, job['root'])
                if snapshot is not None:
                    with snapshot:
                        full |= snapshot.complete
                with worker._state_lock:
                    worker._session_checked.discard((worker.database, Path(job['root'])))
            if job['names_only']:
                snapshot = worker.get(job['root'], validate_files=False, cancelled=interrupted, report=report)
            else:
                snapshot = worker.reconcile_folder(job['root'], changes=json.loads(job['changes']),
                                                  full=full, recursive_initial=bool(job['recursive']),
                                                  cancelled=interrupted, report=report)
            if snapshot is not None:
                snapshot.close()
            check_cancelled(cancelled)
        except OperationCancelled:
            self._update(identity, state='pending', message='Yielded at saved folder checkpoints' if yielded
                         else 'Waiting to resume saved folder checkpoints')
        except sqlite3.OperationalError as error:
            if _busy(error):
                raise  # Keep the durable receipt resumable after transient contention.
            self._update(identity, state='error', error=str(error), message='Index unavailable')
        except Exception as error:
            self._update(identity, state='error', error=str(error), message='Index unavailable')
        else:
            self._update(identity, state='done', message='Saved progressive folder totals')
