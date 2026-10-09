"""Worker snapshots keep database reads and aggregate loading off the GUI thread."""
from time import monotonic
import sqlite3
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
        self.result = (None, "")
        super().__init__(lambda: self._collect(scanner), parent)
        self.status_timer = qt.QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self._tick)
        self.started.connect(self.status_timer.start)
        self.finished.connect(self.status_timer.stop)

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
        if message == 'Saved progressive folder totals':
            self._cached(force=True)

    def _cached(self, *, force=False):
        if self.isInterruptionRequested() or not force and monotonic() - self._last_update < 1:
            return
        snapshot = directory_cache.peek(self.root, cancelled=self.isInterruptionRequested)
        if snapshot is not None:
            self.saved_entries = len(snapshot.entries)
            self._status.update(0, 'Loading saved sizes…', saved_entries=self.saved_entries)
            self.last_progress = self._status.render()
            self.progress.emit(self.last_progress)
            totals = snapshot.folder_stats(children_of=self.root, cancelled=self.isInterruptionRequested)
            self.last_totals = totals
            self.updated.emit(self.root, totals)
            paths = (self.root,) + tuple(entry.path for entry in snapshot.children(self.root, limit=128) if not entry.symlink)
            self.last_paths = paths
            self.watch_paths.emit(self.root, paths)
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
            if not job.subscribers:
                job.requestInterruption()

    def start(self):
        key = (directory_cache.database, self.root)
        if self.request_key is not None:
            key += (self.request_key,)
        job = _jobs.get(key)
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
        job.updated.connect(self.updated)
        job.watch_paths.connect(self.watch_paths)
        job.progress.connect(self.progress)
        self.progress.emit(job.last_progress)
        if job.last_totals is not None: self.updated.emit(self.root, job.last_totals)
        if job.last_paths is not None: self.watch_paths.emit(self.root, job.last_paths)
        if fresh: job.start()

    def _detach(self):
        job = self._job
        self._job = None
        if job is not None:
            job.subscribers.discard(self)
            job.updated.disconnect(self.updated)
            job.watch_paths.disconnect(self.watch_paths)
            job.progress.disconnect(self.progress)
        return job

    def _finish(self, result=None, error=''):
        if self._finished: return
        self._finished = True
        self._detach()
        self.completed.emit(result, error)
        self.finished.emit()

    def requestInterruption(self):
        if self._finished or self._stopped: return
        self._stopped = True
        job = self._detach()
        if job is not None and not job.subscribers:
            job.requestInterruption()
            self._waiting_job = job
            # Keep the final owner alive until the thread has actually stopped.
            job.finished.connect(self._finish)
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
