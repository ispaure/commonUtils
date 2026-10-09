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
    if message.startswith('Optimizing '):
        return 'Optimizing saved index'
    if message.startswith('Preparing '):
        return 'Preparing file index'
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
    if message == 'Saved progressive folder totals' or message.startswith('Saving '):
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
            return (f'File index · {self.saved_entries:,} saved entries'
                    f' · {processed:,} processed this run · {processed / max(.1, elapsed):,.0f} entries/s'
                    f' · {format_duration(elapsed)} elapsed · {self.phase}')


class IndexActivityBar(qt.QProgressBar):
    """Indeterminate activity: a blue track with a moving soft highlight.

    Retains QProgressBar's busy range/accessibility API. The highlight signals
    activity, rather than claiming a known percentage. Hidden bars stop ticking.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 0)
        self.setTextVisible(False)
        self.setFixedSize(140, 10)
        self.setStyleSheet('QProgressBar { min-height: 0px; }')
        self.setAccessibleName('File index activity, total work unknown')
        self.setToolTip('Index work is in progress; the total is not yet known')
        self._started_at = monotonic()
        self._animation = qt.QTimer(self)
        self._animation.setInterval(40)
        self._animation.timeout.connect(self.update)

    def showEvent(self, event):
        super().showEvent(event)
        self._started_at = monotonic()
        self._animation.start()

    def hideEvent(self, event):
        self._animation.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        rect = qt.QRectF(self.contentsRect())
        shape = qt.QPainterPath()
        shape.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.fillPath(shape, self.palette().color(qt.QPalette.ColorRole.Highlight))
        painter.setClipPath(shape)
        band = rect.width() * .55
        phase = ((monotonic() - self._started_at) / 1.4) % 1
        start = rect.left() - band + (rect.width() + band) * phase
        gradient = qt.QLinearGradient(start, 0, start + band, 0)
        gradient.setColorAt(0, qt.QColor(255, 255, 255, 0))
        gradient.setColorAt(.5, qt.QColor(255, 255, 255, 125))
        gradient.setColorAt(1, qt.QColor(255, 255, 255, 0))
        painter.fillRect(rect, gradient)
        painter.end()


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
        self.activity = IndexActivityBar()
        self.refresh_button = qt.QPushButton('Refresh index')
        self.refresh_button.setToolTip('Check all files and saved sizes below the current folder')
        self.refresh_button.clicked.connect(self._refresh_index)
        self.details_button = qt.QPushButton('Index details…')
        self.details_button.setToolTip('Show saved scan errors and unfinished folders for the active tab')
        self.details_button.clicked.connect(self._index_details)
        bar.addWidget(self.label,1); bar.addPermanentWidget(self.activity)
        bar.addPermanentWidget(self.details_button)
        bar.addPermanentWidget(self.refresh_button)
        workspace.active_changed.connect(self.refresh)

    def _refresh_index(self):
        browser = getattr(self.workspace.active_view, 'file_browser', None)
        if browser is not None:
            browser.refresh()

    def _index_details(self):
        browser = getattr(self.workspace.active_view, 'file_browser', None)
        if browser is not None:
            browser.show_index_details()

    def refresh(self, *args):
        browsers = []
        for dock in self.workspace.docks:
            view = dock.widget()
            browser = getattr(view,'file_browser',None)
            if browser is None: continue
            browsers.append((view,browser))
            floating = dock.isFloating()
            browser.workspace_status = not floating
            browser.index_status.setVisible(floating)
            browser.index_details_button.setVisible(floating and browser.index_incomplete)
            browser.index_activity.setVisible(floating and browser.folder_busy and
                                              not getattr(browser, '_loading_cached_only', False))
            browser._update_pause_button()
            if browser not in self.connected:
                self.connected.add(browser)
                browser.index_progress.connect(self.refresh)
                browser.index_state_changed.connect(self.refresh)
                dock.topLevelChanged.connect(self.refresh)
                browser.destroyed.connect(lambda obj=None, owner=browser: self.connected.discard(owner))
        active = self.workspace.active_view
        browser = getattr(active,'file_browser',None)
        running = len({item.folder_operation.root for _,item in browsers if item.folder_busy})
        message = browser.index_status.text() if browser else 'No folder open.'
        if running > 1: message += f' · {running} indexing locations'
        elif running and browser is not None and not browser.folder_busy:
            message += ' · Another tab is indexing'
        self.label.setText(message)
        self.label.setToolTip(message)
        self.activity.setVisible(bool(running))
        self.refresh_button.setVisible(browser is not None and not running)
        self.refresh_button.setEnabled(browser is not None and browser.calculate_folder_sizes)
        self.details_button.setVisible(browser is not None and browser.index_incomplete)
