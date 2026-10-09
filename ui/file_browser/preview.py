"""Details shared by sidebar and column previews; established fields stay available."""
from .. import pyside as qt


class PreviewCover(qt.QLabel):
    resized = qt.Signal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()


def create_preview_panel(browser):
    """Populate the established browser widget attributes for extension compatibility."""
    browser.preview_panel = qt.QWidget()
    browser.preview_panel.setMinimumWidth(220)
    panel_layout = qt.QVBoxLayout(browser.preview_panel)
    header = qt.QHBoxLayout()
    browser.heading = qt.QLabel('Files')
    browser.heading.setTextFormat(qt.Qt.TextFormat.PlainText)
    browser.heading.setWordWrap(True)
    header.addWidget(browser.heading, 1)
    panel_layout.addLayout(header)
    browser.message = qt.QLabel('Select a file or folder.')
    browser.message.setTextFormat(qt.Qt.TextFormat.PlainText)
    browser.message.setWordWrap(True)
    panel_layout.addWidget(browser.message)
    browser.cover = PreviewCover()
    browser.cover.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
    browser.cover.setMinimumSize(180, 200)
    browser.cover.setMaximumHeight(500)
    browser.cover.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Preferred)
    browser.cover.resized.connect(browser._scale_cover)
    panel_layout.addWidget(browser.cover)
    browser.tabs = qt.QTabWidget()
    browser.tabs.setDocumentMode(True)
    panel_layout.addWidget(browser.tabs, 1)
    browser._empty_preview = qt.QPlainTextEdit()
    browser._empty_preview.setReadOnly(True)
    browser.splitter.addWidget(browser.preview_panel)
    browser.splitter.setStretchFactor(0, 7)
    browser.splitter.setStretchFactor(1, 3)
    browser.preview_panel.hide()


def update_preview_visibility(browser, selected):
    """Use a native final column, a details sidebar, or storage's own ranked list."""
    mode = browser._preview_mode()
    columns = browser.views.columns
    browser.preview_toggle.setVisible(mode in (0, 1))
    if mode == 2:
        from ...dirUtils import Directory
        items = browser.selected_objects()
        visible = len(items) == 1 and not isinstance(items[0], Directory)
        if browser.preview_panel.parentWidget() is not columns.preview_container:
            browser.preview_panel.setMinimumWidth(0)
            columns.preview_layout.addWidget(browser.preview_panel)
        columns.set_file_preview_visible(visible)
        browser.preview_panel.setVisible(visible)
        return
    columns.set_file_preview_visible(False)
    if browser.preview_panel.parentWidget() is not browser.splitter:
        browser.splitter.addWidget(browser.preview_panel)
        browser.preview_panel.setMinimumWidth(220)
    visible = mode != 3 and browser.preview_toggle.isChecked() and browser.navigation.directory is not None
    opening = visible and browser.preview_panel.isHidden()
    browser.preview_panel.setVisible(visible)
    if opening:
        width = max(1, browser.splitter.width())
        details = min(max(220, round(width * .3)), max(220, width - 300))
        browser.splitter.setSizes([max(1, width - details), details])
