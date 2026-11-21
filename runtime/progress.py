"""Thread-safe progress coalescing onto a caller-owned asyncio loop."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from threading import Lock


class CoalescedProgress:
    def __init__(self, loop, changed, *, active=lambda: True, interval=.05):
        if interval < 0:
            raise ValueError('Progress interval must be nonnegative')
        self.loop, self.changed, self.active, self.interval = loop, changed, active, interval
        self.lock = Lock()
        self.closed = self.pending = False
        self.latest = None
        self.handle = None

    def publish(self, completed=None, total=None):
        with self.lock:
            if self.closed:
                return
            self.latest = completed, total
            if self.pending:
                return
            self.pending = True
        self.loop.call_soon_threadsafe(self.schedule)

    def schedule(self):
        if not self.closed:
            self.handle = self.loop.call_later(self.interval, self.flush)

    def flush(self):
        with self.lock:
            self.pending = False
            latest = self.latest
        if not self.closed and self.active() and latest is not None:
            self.changed(*latest)

    def close(self):
        with self.lock:
            self.closed = True
        if self.handle is not None:
            self.handle.cancel()
