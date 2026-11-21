"""Browser action and retained SQLite window ownership."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from pathlib import Path
from .. import pyside as qt
from .access import check_access, is_candidate, provider_path


def managed_index_paths():
    from ...filesystem.index import directory_index_path
    from ...filesystem import index
    paths = [directory_index_path()]
    # Consult an existing cache only; admission must not create an index owner.
    cache = vars(index).get('directory_cache')
    if cache is not None:
        paths.append(cache.database)
    return tuple(path for database in paths for path in (database, database.with_suffix('.jobs.sqlite3')))


class SQLiteController(qt.QObject):
    idle = qt.Signal()

    def __init__(self, browser, *, provider=None, write_allowed=None, readonly_paths=()):
        super().__init__(browser)
        self.browser = browser
        self.provider = provider
        self.write_allowed = write_allowed
        self.readonly_paths = readonly_paths
        self.windows = []
        self.closing = False

    @property
    def busy(self):
        return any(window.busy for window in self.windows)

    @property
    def can_retire(self):
        return all(window.can_retire for window in self.windows)

    def available(self, path):
        # Do not perform provider or database I/O while constructing a menu.
        return (not self.closing and is_candidate(path) and
                (self.provider is None or (not getattr(self.provider, 'private', False)
                 and callable(type(self.provider).__dict__.get('sqlite_local_path')))))

    def actions(self, item, context):
        from ...filesystem import BrowserAction
        from ...filesystem.files import File
        if isinstance(item, File) and len(context.selection) == 1 and self.available(item.path):
            return (BrowserAction('commonutils.sqlite.inspect', 'Inspect SQLite…',
                    lambda captured: self.open(captured.selection[0].path), source='SQLite'),)
        return ()

    def open(self, path):
        if self.closing:
            return None
        from .window import SQLiteBrowser
        logical = Path(path)
        provider, policy, extra = self.provider, self.write_allowed, self.readonly_paths
        # Provider resolution also runs on the worker, before it can open data.
        # The window path is the logical path for LocalFiles; a custom hook may
        # only opt in when it maps to this same ordinary file, never a copy.
        def access_check(*, writable=False):
            physical = provider_path(provider, logical, writable=writable) if provider is not None else logical.absolute()
            if physical != logical.absolute():
                raise PermissionError('SQLite access requires a direct local resource, without mapping or copy-back.')
            additional = extra() if callable(extra) else extra
            return check_access(physical, writable=writable, write_allowed=policy,
                                readonly_paths=(*managed_index_paths(), *additional))
        window = SQLiteBrowser(logical, self.browser, writable=policy is not None, access_check=access_check)
        self.windows.append(window)
        window.idle.connect(self.idle)
        window.destroyed.connect(lambda: self._retired(window))
        window.saved.connect(self.browser.refresh)
        window.show()
        return window

    def _retired(self, window):
        if window in self.windows:
            self.windows.remove(window)
        self.idle.emit()

    def prepare_close(self):
        self.closing = True
        ready = True
        for window in tuple(self.windows):
            # closeEvent owns the Save / Discard / Cancel prompt. Busy windows
            # retry their own close after the worker has fully retired.
            if not window.close():
                ready = False
        if not ready and not any(window.close_pending for window in self.windows):
            self.closing = False
        return ready

    def wait(self):
        """Final application shutdown joins workers without destroying owners."""
        for window in tuple(self.windows):
            operation = window.operation
            operation.request_cancel()
            if operation.operation is not None:
                operation.operation.thread.wait()
