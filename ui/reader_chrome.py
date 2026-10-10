"""Shared reader presentation: scalable icons, controls and window-state handling.

No format/loading/navigation policy lives here. Hosts retain their public widget
handles and supply actions; both text and image readers use the same geometry.
"""
from . import pyside as qt

READER_MARGINS = (8, 2, 8, 3)
READER_SPACING = 4


class ReaderIcon(qt.QIconEngine):
    """Palette-aware line icons with identical appearance across platforms."""
    def __init__(self, name):
        super().__init__()
        self.name = name

    def clone(self):
        return ReaderIcon(self.name)

    def paint(self, painter, rect, mode, state):
        painter.save()
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        painter.translate(rect.x(), rect.y())
        painter.scale(rect.width() / 24, rect.height() / 24)
        palette = qt.QApplication.palette()
        group = qt.QPalette.ColorGroup.Disabled if mode == qt.QIcon.Mode.Disabled else qt.QPalette.ColorGroup.Active
        role = (qt.QPalette.ColorRole.Highlight if state == qt.QIcon.State.On and mode != qt.QIcon.Mode.Disabled
                else qt.QPalette.ColorRole.ButtonText)
        pen = qt.QPen(palette.color(group, role), 1.7)
        pen.setCapStyle(qt.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(qt.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(qt.Qt.BrushStyle.NoBrush)
        if self.name == 'fullscreen':
            for x, y, sx, sy in ((4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1), (20, 20, -1, -1)):
                if state == qt.QIcon.State.On:
                    x, y, sx, sy = x + sx * 5, y + sy * 5, -sx, -sy
                painter.drawLine(qt.QLineF(x, y, x + sx * 5, y))
                painter.drawLine(qt.QLineF(x, y, x, y + sy * 5))
        elif self.name == 'up':
            painter.drawPolyline([qt.QPointF(5, 15), qt.QPointF(12, 9), qt.QPointF(19, 15)])
        elif self.name in ('previous', 'next', 'previous-file', 'next-file'):
            forward = self.name.startswith('next')
            x, dx = (15, -6) if forward else (9, 6)
            painter.drawPolyline([qt.QPointF(x + dx, 5), qt.QPointF(x, 12), qt.QPointF(x + dx, 19)])
            if self.name.endswith('file'):
                stop = 19 if forward else 5
                painter.drawLine(qt.QLineF(stop, 5, stop, 19))
        elif self.name == 'sidebar':
            painter.drawRoundedRect(qt.QRectF(3, 4, 18, 16), 1.5, 1.5)
            painter.drawLine(qt.QLineF(9, 4, 9, 20))
            for y in (8, 12, 16):
                painter.drawLine(qt.QLineF(5, y, 7, y))
        elif self.name == 'appearance':
            font = qt.QFont(painter.font())
            font.setPixelSize(17)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(qt.QRectF(1, 0, 22, 24), qt.Qt.AlignmentFlag.AlignCenter, 'Aa')
        elif self.name == 'layout':
            painter.drawRoundedRect(qt.QRectF(3, 4, 18, 16), 1.5, 1.5)
            painter.drawLine(qt.QLineF(12, 4, 12, 20))
        elif self.name == 'play':
            painter.drawPolygon([qt.QPointF(7, 4), qt.QPointF(20, 12), qt.QPointF(7, 20)])
        elif self.name == 'pause':
            painter.drawRoundedRect(qt.QRectF(6, 4, 4, 16), 1, 1)
            painter.drawRoundedRect(qt.QRectF(14, 4, 4, 16), 1, 1)
        elif self.name == 'stop':
            painter.drawRoundedRect(qt.QRectF(5, 5, 14, 14), 1, 1)
        elif self.name == 'edit':
            painter.drawPolygon([qt.QPointF(4, 16), qt.QPointF(16, 4), qt.QPointF(20, 8),
                                 qt.QPointF(8, 20), qt.QPointF(3, 21)])
            painter.drawLine(qt.QLineF(13, 7, 17, 11))
        elif self.name == 'read':
            painter.drawRoundedRect(qt.QRectF(5, 3, 14, 18), 1, 1)
            for y in (8, 12, 16):
                painter.drawLine(qt.QLineF(8, y, 16, y))
        elif self.name == 'close':
            painter.drawLine(qt.QLineF(6, 6, 18, 18))
            painter.drawLine(qt.QLineF(18, 6, 6, 18))
        painter.restore()

    def pixmap(self, size, mode, state):
        pixmap = qt.QPixmap(size)
        pixmap.fill(qt.Qt.GlobalColor.transparent)
        painter = qt.QPainter(pixmap)
        self.paint(painter, pixmap.rect(), mode, state)
        painter.end()
        return pixmap


def reader_icon(name):
    return qt.QIcon(ReaderIcon(name))


def reader_button(parent, name, *, action=None, icon=None, text=None):
    """Consistent 32-pixel controls; clicks leave reading-pane keyboard focus alone."""
    button = qt.QToolButton(parent)
    if action is not None:
        if icon:
            action.setIcon(reader_icon(icon))
        button.setDefaultAction(action)
    elif icon:
        button.setIcon(reader_icon(icon))
    button.setIconSize(qt.QSize(20, 20))
    button.setAutoRaise(True)
    button.setFocusPolicy(qt.Qt.FocusPolicy.TabFocus)
    button.setMinimumHeight(32)
    button.setMinimumWidth(32)
    button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonIconOnly if icon else qt.Qt.ToolButtonStyle.ToolButtonTextOnly)
    if text:
        button.setText(text)
    def sync():
        label = action.text().replace('&', '') if action is not None and icon == 'fullscreen' else name
        shortcut = action.shortcut().toString(qt.QKeySequence.SequenceFormat.NativeText) if action is not None else ''
        button.setAccessibleName(label)
        button.setToolTip(f'{label} ({shortcut})' if shortcut else label)
    sync()
    if action is not None:
        action.changed.connect(sync)
    return button


class ReaderLabel(qt.QLabel):
    """Single-line title/status with full text in its tooltip and accessible value."""
    def __init__(self, text='', parent=None, *, muted=False):
        super().__init__(text, parent)
        self.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setMinimumHeight(24)
        if muted:
            self.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)
        self.setToolTip(text)

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(0)
        return hint

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        color = self.palette().color(self.foregroundRole())
        painter.setPen(color)
        text = self.fontMetrics().elidedText(self.text(), qt.Qt.TextElideMode.ElideMiddle, self.contentsRect().width())
        painter.drawText(self.contentsRect(), self.alignment(), text)


class ReaderFullscreen(qt.QObject):
    """Keep action/icon state aligned with native full screen; restore maximization."""
    def __init__(self, owner, action):
        super().__init__(owner)
        self.owner = owner
        self.action = action
        self._window = None
        self._maximized = False
        action.setIcon(reader_icon('fullscreen'))
        self.sync()

    def window(self):
        window = self.owner.window()
        if window is not self._window:
            if self._window is not None:
                self._window.removeEventFilter(self)
            self._window = window
            window.installEventFilter(self)
        return window

    def sync(self):
        active = self.window().isFullScreen()
        self.action.setChecked(active)
        self.action.setText('Exit full screen' if active else 'Full screen')

    def toggle(self):
        window = self.window()
        if window.isFullScreen():
            self.leave()
        else:
            self._maximized = window.isMaximized()
            window.showFullScreen()
            self.sync()

    def leave(self):
        window = self.window()
        if window.isFullScreen():
            window.showMaximized() if self._maximized else window.showNormal()
        self.sync()

    def eventFilter(self, watched, event):
        if event.type() == qt.QEvent.Type.WindowStateChange:
            if self.window().isFullScreen() and not event.oldState() & qt.Qt.WindowState.WindowFullScreen:
                self._maximized = bool(event.oldState() & qt.Qt.WindowState.WindowMaximized)
            self.sync()
        return False
