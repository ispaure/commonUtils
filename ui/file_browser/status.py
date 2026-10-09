"""Single-line status text that keeps progress counters and elides long paths."""
from .. import pyside as qt


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
        for prefix in ('Indexing ', 'Checking file metadata · ', 'Checking indexed folder ', 'Reusing saved branch '):
            if text.startswith(prefix):
                path, separator, suffix = text[len(prefix):].partition(' · ')
                tail = separator+suffix
                remaining = width-metrics.horizontalAdvance(prefix+tail)
                if remaining > metrics.horizontalAdvance('…'):
                    text = prefix+metrics.elidedText(path,qt.Qt.TextElideMode.ElideMiddle,remaining)+tail
                break
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
        self.label.setToolTip('\n'.join(f'{view.view_title}: {item.index_status.text()}' for view,item in browsers))
        self.activity.setVisible(bool(running))
