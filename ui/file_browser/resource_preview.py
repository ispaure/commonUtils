"""Provider selection details using the established browser preview widgets."""
from threading import Event
from .. import pyside as qt
from ..tasks.operations import Operation
from .details import DetailsPanel
from .preview import create_preview_panel, update_preview_visibility
from ...filesystem import format_size
from ...runtime.browsing import BrowseRole


class ResourcePreview(qt.QObject):
    def __init__(self, browser, loader=None):
        super().__init__(browser)
        self.browser, self.loader = browser, loader
        self.busy = False
        self.closing = False
        self.epoch = 0
        self.cancelled = Event()
        self.queued = False
        self.pending = False
        browser.cover_pixmap = qt.QPixmap()
        browser._scale_cover = self.scale_cover
        browser._preview_mode = browser.views.currentIndex
        create_preview_panel(browser)
        browser.views.selection_changed.connect(self.request)
        browser.directory_changed.connect(self.request)
        browser.preview_toggle.toggled.connect(self.request)
        self.request()

    def request(self, *_):
        if self.closing:
            return
        self.epoch += 1
        self.pending = True
        if self.busy:
            self.cancelled.set()
        if not self.queued:
            self.queued = True
            qt.QTimer.singleShot(0, self, self._start)

    def _start(self):
        self.queued = False
        if self.closing or self.busy or not self.pending:
            return
        self.pending = False
        browser = self.browser
        rows = browser.selected_rows()
        update_preview_visibility(browser, bool(rows))
        if browser.preview_panel.isHidden():
            return
        while browser.tabs.count():
            widget = browser.tabs.widget(0)
            browser.tabs.removeTab(0)
            widget.deleteLater()
        browser.cover_pixmap = qt.QPixmap()
        browser.cover.clear()
        if len(rows) > 1:
            browser.heading.setText(f'{len(rows)} selected items')
            browser.message.setText('Select one item to see its information.')
            return
        row = dict(rows[0]) if rows else dict(name=browser.navigation.directory.name,
            path=browser.provider.relative(browser.navigation.directory), directory=True,
            modified='', size=None)
        browser.heading.setText(row['name'])
        fields = [('Name', row['name']), ('Location', row['path'] or '/'),
                  ('Type', 'Folder' if row['directory'] else 'File')]
        if not row['directory'] and row.get('size') is not None:
            fields.append(('Size', format_size(row['size'])))
        if row.get('modified'):
            fields.append(('Modified', row['modified']))
        browser.tabs.addTab(DetailsPanel(fields), 'File Information')
        icon = browser.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon if row['directory'] else qt.QStyle.StandardPixmap.SP_FileIcon)
        browser.cover.setPixmap(icon.pixmap(96, 96))
        browser.cover.setMinimumSize(96, 96)
        browser.cover.setMaximumHeight(120)
        browser.message.clear()
        if not self.loader or row['directory']:
            return
        self.busy = True
        self.cancelled = Event()
        epoch, cancelled = self.epoch, self.cancelled
        browser.message.setText('Loading information…')
        self.operation = Operation(lambda: self.loader(row, cancelled.is_set), self)
        self.operation.completed.connect(lambda result, error: self._loaded(epoch, result, error))
        self.operation.finished.connect(self._finished)
        self.operation.start()

    def _loaded(self, epoch, result, error):
        if self.closing or epoch != self.epoch:
            return
        browser = self.browser
        browser.message.setText(error)
        for title, details in result or ():
            browser.tabs.addTab(DetailsPanel(details.fields), title)
            if details.message:
                browser.message.setText(details.message)
            if details.thumbnail:
                browser.cover_pixmap.loadFromData(details.thumbnail)
        if browser.tabs.count() > 1:
            browser.tabs.setCurrentIndex(browser.tabs.count() - 1)
        if not browser.cover_pixmap.isNull():
            browser.cover.setMinimumSize(180, 200)
            browser.cover.setMaximumHeight(500)
            self.scale_cover()

    def scale_cover(self):
        browser = self.browser
        if browser.cover_pixmap.isNull():
            return
        ratio = browser.devicePixelRatioF()
        pixmap = browser.cover_pixmap.scaled(round(min(320, max(1, browser.cover.width())) * ratio), round(440 * ratio),
            qt.Qt.AspectRatioMode.KeepAspectRatio, qt.Qt.TransformationMode.SmoothTransformation)
        pixmap.setDevicePixelRatio(ratio)
        browser.cover.setPixmap(pixmap)

    def _finished(self):
        self.busy = False
        self.operation.deleteLater()
        if self.pending and not self.closing:
            self._start()
        self.browser._maybe_idle()

    def stop(self):
        self.closing = True
        self.pending = False
        self.epoch += 1
        self.cancelled.set()
        self.browser.cover_pixmap = qt.QPixmap()
        self.browser.cover.clear()

    def resume(self):
        self.closing = False
        self.request()
