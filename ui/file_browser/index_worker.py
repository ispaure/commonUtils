"""Worker snapshots keep database reads and aggregate loading off the GUI thread."""
from time import monotonic
import sqlite3
from threading import Event, RLock
from ..operations import Operation
from .. import pyside as qt
from ...directory_index import directory_cache
from .status import IndexProgress


class _IndexJob(Operation):
    updated = qt.Signal(object, object)
    watch_paths = qt.Signal(object, object)
    progress = qt.Signal(str)

    def __init__(self, root, scanner, parent):
        self.root = root
        self._last_update = 0
        self.started_at = monotonic()
        self._last_progress = 0
        self._status = IndexProgress(self.started_at)
        self.saved_entries = 0
        self.last_progress = "Waiting for index writer…"
        self.last_totals = None
        self.last_paths = None
        self.subscribers = set()
        self._view_lock = RLock()
        self._view_roots = {}
        self._cache_requested = Event()
        self.totals_by_root = {}
        self.paths_by_root = {}
        self.result = (None, "")
        super().__init__(lambda: self._collect(scanner), parent)
        self.status_timer = qt.QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self._tick)
        self.started.connect(self.status_timer.start)
        self.finished.connect(self.status_timer.stop)

    def set_view_root(self, owner, root=None):
        with self._view_lock:
            if root is None:
                self._view_roots.pop(owner, None)
            else:
                self._view_roots[owner] = root
        self._cache_requested.set()

    def _tick(self):
        if self.isRunning():
            self.progress.emit(self._status.render())

    def _collect(self, scanner):
        try:
            self._cached(force=True)
        except sqlite3.OperationalError:
            # A second tab can read while the first creates the database/schema.
            # Cached display is optional; always proceed to the serialized scan.
            pass
        result = scanner(self.root, self.isInterruptionRequested, report=self._report, reuse_for=30)
        if not self.isInterruptionRequested():
            self._cached(force=True)
        return result

    def _report(self, done, total, message):
        now = monotonic()
        self._status.update(done, message, saved_entries=self.saved_entries)
        if now - self._last_progress >= .2 or done == 0:
            self._last_progress = now
            self.last_progress = self._status.render(now)
            self.progress.emit(self.last_progress)
        if message == 'Saved progressive folder totals' or self._cache_requested.is_set():
            self._cache_requested.clear()
            self._cached(force=True)

    def _cached(self, *, force=False):
        if self.isInterruptionRequested() or not force and monotonic() - self._last_update < 1:
            return
        with self._view_lock:
            roots = tuple(dict.fromkeys((self.root,) + tuple(self._view_roots.values())))
        source = directory_cache.peek(self.root, cancelled=self.isInterruptionRequested)
        for root in roots:
            if self.isInterruptionRequested():
                return
            # Every view follows this worker's generation, even if an older
            # independently indexed child root also exists in the database.
            snapshot = source or directory_cache.peek(root, cancelled=self.isInterruptionRequested)
            if snapshot is None:
                continue
            totals = snapshot.folder_stats(children_of=root, cancelled=self.isInterruptionRequested)
            if root == self.root:
                stats = totals.get(root)
                self.saved_entries = stats.files + stats.folders if stats else 0
                self._status.update(0, self._status.phase, saved_entries=self.saved_entries)
                self.last_progress = self._status.render()
                self.progress.emit(self.last_progress)
            changed = self.totals_by_root.get(root) != totals
            self.totals_by_root[root] = totals
            if root == self.root:
                self.last_totals = totals
            if changed:
                self.updated.emit(root, totals)
            failed = {path for path, error in snapshot.errors}
            def watchable(path):
                return path not in failed and not any(parent in failed for parent in path.parents)
            # Failed paths stay visible in diagnostics, but do not generate an
            # endless stream of automatic retry jobs. Refresh retries explicitly.
            candidates = (root,) + tuple(entry.path for entry in snapshot.children(root, limit=128) if not entry.symlink)
            paths = tuple(path for path in candidates if watchable(path))
            self.paths_by_root[root] = paths
            if root == self.root:
                self.last_paths = paths
            self.watch_paths.emit(root, paths)
        self._last_update = monotonic()


_jobs = {}


class FolderOperation(qt.QObject):
    """One browser's subscription to a shared per-location indexing worker.

    Cancelling a subscription never cancels another browser's work. The last
    subscriber cancels the worker; its durable checkpoints remain resumable.
    """
    updated = qt.Signal(object, object)
    watch_paths = qt.Signal(object, object)
    progress = qt.Signal(str)
    completed = qt.Signal(object, str)
    finished = qt.Signal()

    def __init__(self, root, scanner, parent, *, request_key=None):
        super().__init__(parent)
        self.root = root
        self.visible_root = root
        self.scanner = scanner
        self.request_key = request_key
        self.started_at = monotonic()
        self._job = None
        self._waiting_job = None
        self._stopped = False
        self._finished = False
        self.destroyed.connect(lambda: self._owner_destroyed())

    def _owner_destroyed(self):
        # Also cover a host deleting its widget directly instead of closing it.
        job = self._job
        self._job = None
        if job is not None:
            job.subscribers.discard(self)
            job.set_view_root(self)
            if not job.subscribers:
                job.requestInterruption()

    def start(self):
        key = (directory_cache.database, self.root)
        if self.request_key is not None:
            key += (self.request_key,)
        job = _jobs.get(key)
        if job is None and self.request_key == ('reconcile', ()):
            candidates = [owner for identity,owner in tuple(_jobs.items())
                          if identity[0] == directory_cache.database and len(identity) == 3
                          and isinstance(identity[2], tuple) and identity[2][0] == 'reconcile'
                          and (owner.root == self.root or owner.root in self.root.parents)
                          and not owner.isInterruptionRequested()]
            if candidates:
                job = max(candidates, key=lambda owner: len(owner.root.parts))
                self.root = job.root
        if job is None or job.isInterruptionRequested():
            job = _IndexJob(self.root, self.scanner, qt.QApplication.instance())
            _jobs[key] = job
            job.completed.connect(lambda result, error, owner=job: setattr(owner, 'result', (result,error)))
            def finish(owner=job):
                if _jobs.get(key) is owner: del _jobs[key]
                for subscriber in tuple(owner.subscribers): subscriber._finish(*owner.result)
                owner.deleteLater()
            job.finished.connect(finish)
            fresh = True
        else:
            fresh = False
        self._job = job
        job.subscribers.add(self)
        job.set_view_root(self, self.visible_root)
        job.updated.connect(self.updated)
        job.watch_paths.connect(self.watch_paths)
        job.progress.connect(self.progress)
        self.progress.emit(job.last_progress)
        if self.visible_root in job.totals_by_root:
            self.updated.emit(self.visible_root, job.totals_by_root[self.visible_root])
        if self.visible_root in job.paths_by_root:
            self.watch_paths.emit(self.visible_root, job.paths_by_root[self.visible_root])
        if fresh: job.start()

    def retarget(self, root):
        """Follow a descendant view while the original shared scan keeps running."""
        job = self._job
        if job is None or self._stopped or self._finished:
            return False
        if root != job.root and job.root not in root.parents:
            return False
        self.visible_root = root
        job.set_view_root(self, root)
        if root in job.totals_by_root:
            self.updated.emit(root, job.totals_by_root[root])
        if root in job.paths_by_root:
            self.watch_paths.emit(root, job.paths_by_root[root])
        return True

    def _detach(self):
        job = self._job
        self._job = None
        if job is not None:
            job.subscribers.discard(self)
            job.set_view_root(self)
            job.updated.disconnect(self.updated)
            job.watch_paths.disconnect(self.watch_paths)
            job.progress.disconnect(self.progress)
        return job

    def _finish(self, result=None, error=''):
        if self._finished: return
        self._finished = True
        job = self._job
        if result is not None and job is not None and self.visible_root != job.root:
            result = job.totals_by_root.get(self.visible_root)
        self._detach()
        self.completed.emit(result, error)
        self.finished.emit()

    def requestInterruption(self):
        if self._finished or self._stopped: return
        self._stopped = True
        job = self._detach()
        if job is not None and not job.subscribers:
            self._waiting_job = job
            # Connect before cancelling. A fast worker may already have emitted
            # finished while its queued GUI callback has not run yet.
            job.finished.connect(self._finish)
            job.requestInterruption()
            if job.isFinished():
                qt.QTimer.singleShot(0, self._finish)
        else:
            qt.QTimer.singleShot(0, self._finish)

    def isInterruptionRequested(self):
        return self._stopped

    def isRunning(self):
        job = self._waiting_job or self._job
        try: return not self._finished and job is not None and job.isRunning()
        except RuntimeError: return False

    def isFinished(self):
        return self._finished

    def wait(self, *args):
        job = self._waiting_job or self._job
        if job is not None:
            try: return job.wait(*args)
            except RuntimeError: pass
        return True
