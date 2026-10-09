"""Path-free indexing presentation shared by standalone and workspace browsers."""
import re
from threading import RLock
from time import monotonic
from .. import pyside as qt


def format_duration(seconds):
    """Compact elapsed time, retaining seconds even for hour-long operations."""
    hours, remainder = divmod(max(0, int(seconds)), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f'{hours}h {minutes:02d}m {seconds:02d}s'
    if minutes:
        return f'{minutes}m {seconds:02d}s'
    return f'{seconds}s'


def indexing_phase(message):
    """Never expose scanner-supplied paths or errors in the shared status line."""
    if message.startswith('Waiting '):
        return 'Waiting for index writer'
    if message.startswith('Loading '):
        return 'Loading saved sizes'
    if message.startswith('Using recently '):
        return 'Reusing saved index'
    if message.startswith('Checking '):
        return 'Checking indexed files'
    if message.startswith('Reusing '):
        return 'Reusing saved index'
    if message == 'Saved progressive folder totals':
        return 'Saving folder sizes'
    return 'Indexing files'


_COUNTER = re.compile(r'(?:[\d,]+ (?:saved entries|processed this run|entries/s|entries in this folder)'
                      r'|(?:\d+h )?(?:\d+m )?\d+s elapsed)\Z')


def private_status(message):
    """Also protect direct progress publishers using the older path-bearing API."""
    if message.startswith(('Indexing ', 'Checking ', 'Reusing ')) and not message.startswith('Indexing paused'):
        parts = message.split(' · ')
        counters = [part for part in parts[1:] if _COUNTER.fullmatch(part)]
        return ' · '.join([indexing_phase(parts[0])] + counters)
    return message


class IndexProgress:
    """Thread-safe counters; GUI ticks keep elapsed time live during long SQL work.

    Processed counts include both discovery and validation metadata operations,
    and never fall back to zero when switching phases. Speed is the run average.
    """
    def __init__(self, started_at=None):
        self.started_at = monotonic() if started_at is None else started_at
        self.phase = 'Waiting for index writer'
        self.saved_entries = 0
        self.counts = {}
        self.lock = RLock()

    def update(self, done, message, *, saved_entries=None):
        with self.lock:
            self.phase = indexing_phase(message)
            if self.phase in ('Indexing files', 'Checking indexed files'):
                self.counts[self.phase] = max(done, self.counts.get(self.phase, 0))
            if saved_entries is not None:
                self.saved_entries = saved_entries

    def render(self, now=None):
        with self.lock:
            elapsed = (monotonic() if now is None else now) - self.started_at
            processed = sum(self.counts.values())
            return (f'{self.phase} · {self.saved_entries:,} saved entries'
                    f' · {processed:,} processed this run · {processed / max(.1, elapsed):,.0f} entries/s'
                    f' · {format_duration(elapsed)} elapsed')


class IndexStatusLabel(qt.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_text = ''
        self.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.setWordWrap(False)
        self.setSizePolicy(qt.QSizePolicy.Policy.Ignored,qt.QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)

    def setText(self, text):
        self.full_text = text
        self.setToolTip(text)
        self._fit()

    def text(self):
        return self.full_text

    def _fit(self):
        metrics = self.fontMetrics()
        width = max(0,self.contentsRect().width())
        text = self.full_text
        super().setText(metrics.elidedText(text,qt.Qt.TextElideMode.ElideMiddle,width))

    def resizeEvent(self, event):
        super().resizeEvent(event); self._fit()

    def changeEvent(self, event):
        super().changeEvent(event); self._fit()

    def minimumSizeHint(self):
        return qt.QSize(0, self.fontMetrics().height()+4)


class WorkspaceIndexStatus(qt.QObject):
    """A workspace owns one status line, even with multiple visible browser tabs."""
    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.connected = set()
        bar = workspace.statusBar()
        bar.setSizeGripEnabled(False)
        self.label = IndexStatusLabel()
        self.label.setAccessibleName('Workspace indexing status')
        self.activity = qt.QProgressBar()
        self.activity.setRange(0,0); self.activity.setTextVisible(False)
        self.activity.setFixedWidth(70); self.activity.setMaximumHeight(10)
        bar.addWidget(self.label,1); bar.addPermanentWidget(self.activity)
        workspace.active_changed.connect(self.refresh)

    def refresh(self, *args):
        browsers = []
        for dock in self.workspace.docks:
            view = dock.widget()
            browser = getattr(view,'file_browser',None)
            if browser is None: continue
            browsers.append((view,browser))
            browser.workspace_status = True
            browser.index_status.hide(); browser.index_activity.hide()
            if browser not in self.connected:
                self.connected.add(browser)
                browser.index_progress.connect(self.refresh)
                browser.index_state_changed.connect(self.refresh)
                browser.destroyed.connect(lambda obj=None, owner=browser: self.connected.discard(owner))
        active = self.workspace.active_view
        browser = getattr(active,'file_browser',None)
        running = len({item.folder_root for _,item in browsers if item.folder_busy})
        message = browser.index_status.text() if browser else 'No folder open.'
        if running > 1: message += f' · {running} indexing locations'
        elif running and browser is not None and not browser.folder_busy:
            message += ' · Another tab is indexing'
        self.label.setText(message)
        self.label.setToolTip(message)
        self.activity.setVisible(bool(running))
