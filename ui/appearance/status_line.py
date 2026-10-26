"""Shared compact status footers, matching the File Browser presentation."""
from .. import pyside as qt
from .styling import styling
from weakref import ref
from shiboken6 import isValid


class StatusLine(qt.QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(parent)
        self.full_text = str(text)
        self._styling_status = False
        self.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.setMinimumWidth(0)
        self.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Fixed)
        self.setContentsMargins(10, 6, 10, 6)
        styling().bind(self, 'ui', self._appearance)
        self.setText(text)

    def _appearance(self):
        if self._styling_status:
            return
        self._styling_status = True
        color = self.palette().color(qt.QPalette.ColorRole.PlaceholderText).name()
        self.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)
        font = styling().font('ui')
        font.setItalic(True)
        self.setFont(font)
        self.setStyleSheet(f'QLabel {{ color: {color}; font-size: {font.pointSizeF()}pt; font-style: italic; }}')
        self._fit()
        self._styling_status = False

    def setWordWrap(self, enabled):
        super().setWordWrap(False)

    def setText(self, text):
        self.full_text = str(text)
        self.setToolTip(self.full_text)
        self.setAccessibleDescription(self.full_text)
        self._fit()

    def clear(self):
        self.setText('')

    def text(self):
        return self.full_text

    def _fit(self):
        super().setText(self.fontMetrics().elidedText(self.full_text.replace('\n', ' · '),
            qt.Qt.TextElideMode.ElideMiddle, max(0, self.contentsRect().width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == qt.QEvent.Type.PaletteChange:
            self._appearance()
        else:
            self._fit()

    def sizeHint(self):
        margins = self.contentsMargins()
        return qt.QSize(0, self.fontMetrics().height() + margins.top() + margins.bottom() + 4)

    def minimumSizeHint(self):
        return self.sizeHint()


class StatusFooter(qt.QWidget):
    """One-line panel footer with an elided message and optional trailing controls.

    Append controls with ``layout().addWidget(control)``. The footer keeps its
    natural row height while the panel's main content takes the remaining space.
    """
    def __init__(self, text='', parent=None):
        super().__init__(parent)
        self.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Fixed)
        row = qt.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 10, 0)
        row.setSpacing(6)
        self.message = StatusLine(text, self)
        row.addWidget(self.message, 1)


def style_status_bar(bar):
    """Apply the same font/color to native QStatusBar messages without moving controls."""
    bar.setSizeGripEnabled(False)
    weak = ref(bar)
    def apply():
        bar = weak()
        if bar is None or not isValid(bar):
            return
        color = bar.palette().color(qt.QPalette.ColorRole.PlaceholderText).name()
        font = styling().font('ui')
        font.setItalic(True)
        bar.setFont(font)
        bar.setStyleSheet(f'QStatusBar {{ color: {color}; font-size: {font.pointSizeF()}pt; font-style: italic; }} QStatusBar::item {{ border: none; }}')
    styling().bind(bar, 'ui', apply)
