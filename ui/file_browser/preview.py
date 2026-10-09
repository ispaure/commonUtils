"""Selection preview construction and sizing; FileBrowser retains its public fields."""
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
    """Open at roughly 30%; preserve the user's splitter size until it is hidden."""
    visible = browser.preview_toggle.isChecked() and selected
    opening = visible and browser.preview_panel.isHidden()
    browser.preview_panel.setVisible(visible)
    if opening:
        width = max(1, browser.splitter.width())
        details = min(max(220, round(width * .3)), max(220, width - 300))
        browser.splitter.setSizes([max(1, width - details), details])
