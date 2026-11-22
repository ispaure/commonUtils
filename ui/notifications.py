"""GUI-owned notification events and reusable transient result presentation."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from collections import deque

from ..runtime.notifications import Notice as Notice
from . import pyside as qt


class NotificationCenter(qt.QObject):
    published = qt.Signal(object)
    acknowledged = qt.Signal(str)

    def __init__(self, parent=None, *, limit=100):
        super().__init__(parent)
        self.limit = max(1, limit)
        self.records = {}
        self.unread = set()

    def publish(self, notice):
        if notice.id in self.records:
            return False
        self.records[notice.id] = notice
        self.unread.add(notice.id)
        while len(self.records) > self.limit:
            oldest = next(iter(self.records))
            del self.records[oldest]
            self.unread.discard(oldest)
        self.published.emit(notice)
        return True

    def acknowledge(self, identifier):
        if identifier in self.unread:
            self.unread.remove(identifier)
            self.acknowledged.emit(identifier)


class Toast(qt.QWidget):
    """Plain text, bounded lifetime, optional details action; never a decision prompt."""
    def __init__(self, center, parent=None, *, accepts=lambda notice: True, queue=False):
        super().__init__(parent)
        self.center = center
        self.notice = None
        self.pending = deque(maxlen=center.limit) if queue else None
        self.accepts = accepts
        row = qt.QHBoxLayout(self)
        row.setContentsMargins(4, 0, 4, 0)
        self.label = qt.QLabel()
        self.label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        self.details = qt.QPushButton('Details')
        self.dismiss = qt.QPushButton('Dismiss')
        for widget in (self.label, self.details, self.dismiss):
            row.addWidget(widget)
        self.details.clicked.connect(self.open_details)
        self.dismiss.clicked.connect(self.acknowledge)
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.advance)
        center.published.connect(self.present)
        self.hide()

    def present(self, notice):
        if not self.accepts(notice):
            return
        if self.pending is not None and self.notice is not None:
            self.pending.append(notice)
            return
        self.display(notice)

    def display(self, notice):
        self.notice = notice
        self.label.setText(f'{notice.title}: {notice.message}')
        self.details.setVisible(callable(notice.activate))
        self.show()
        self.timer.start(6000)

    def advance(self):
        self.timer.stop()
        self.notice = None
        if self.pending:
            self.display(self.pending.popleft())
        else:
            self.hide()

    def acknowledge(self):
        if self.notice:
            self.center.acknowledge(self.notice.id)
        self.advance()

    def open_details(self):
        if self.notice and callable(self.notice.activate):
            self.notice.activate()
        self.acknowledge()
