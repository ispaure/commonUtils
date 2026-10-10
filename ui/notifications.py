"""GUI-owned notification events and reusable transient result presentation."""
from dataclasses import dataclass
from . import pyside as qt


@dataclass(frozen=True)
class Notice:
    id: str
    source: str
    title: str
    message: str
    outcome: str = 'success'
    activate: object = None
    native: bool = False


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
    def __init__(self, center, parent=None):
        super().__init__(parent)
        self.center = center
        self.notice = None
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
        self.timer.timeout.connect(self.hide)
        center.published.connect(self.present)
        self.hide()

    def present(self, notice):
        self.notice = notice
        self.label.setText(f'{notice.title}: {notice.message}')
        self.details.setVisible(callable(notice.activate))
        self.show()
        self.timer.start(6000)

    def acknowledge(self):
        if self.notice:
            self.center.acknowledge(self.notice.id)
        self.hide()

    def open_details(self):
        if self.notice and callable(self.notice.activate):
            self.notice.activate()
        self.acknowledge()
