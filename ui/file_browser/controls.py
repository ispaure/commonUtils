"""Scalable, palette-aware icons and compact browser view controls."""

import math
from .. import pyside as qt
from ..icons import set_painted_icon


class ViewIcon(qt.QIconEngine):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode

    def clone(self):
        return ViewIcon(self.mode)

    def paint(self, painter, rect, mode, state):
        painter.save()
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        painter.translate(rect.x(), rect.y())
        painter.scale(rect.width() / 24, rect.height() / 24)
        palette = qt.QApplication.palette()
        role = qt.QPalette.ColorRole.Highlight if state == qt.QIcon.State.On else qt.QPalette.ColorRole.ButtonText
        color = palette.color(qt.QPalette.ColorGroup.Disabled if mode == qt.QIcon.Mode.Disabled else qt.QPalette.ColorGroup.Active, role)
        painter.setPen(qt.QPen(color, 1.6))
        painter.setBrush(qt.Qt.BrushStyle.NoBrush)
        if self.mode == 6:
            painter.drawEllipse(qt.QRectF(3, 3, 12, 12))
            painter.drawLine(qt.QLineF(13, 13, 21, 21))
        elif self.mode == 7:
            painter.drawLine(qt.QLineF(6, 6, 18, 18))
            painter.drawLine(qt.QLineF(18, 6, 6, 18))
        elif self.mode == 1:
            for x in (3, 13):
                for y in (3, 13):
                    painter.drawRoundedRect(qt.QRectF(x, y, 7, 7), 1, 1)
        elif self.mode == 0:
            for y in (5, 12, 19):
                painter.drawEllipse(qt.QPointF(4, y), .8, .8)
                painter.drawLine(qt.QLineF(9, y, 21, y))
        elif self.mode == 4:
            painter.drawRoundedRect(qt.QRectF(2, 4, 20, 16), 1, 1)
            painter.drawLine(qt.QLineF(14, 4, 14, 20))
            for y in (8, 12, 16):
                painter.drawLine(qt.QLineF(17, y, 20, y))
        elif self.mode == 3:
            painter.drawRect(qt.QRectF(2, 3, 20, 18))
            painter.drawLine(qt.QLineF(14, 3, 14, 21))
            painter.drawLine(qt.QLineF(2, 14, 14, 14))
            painter.drawLine(qt.QLineF(14, 10, 22, 10))
        elif self.mode == 5:
            painter.drawEllipse(qt.QRectF(2, 2, 20, 20))
            painter.drawEllipse(qt.QRectF(7, 7, 10, 10))
            for angle in (0, 90, 210):
                x, y = math.cos(math.radians(angle)), math.sin(math.radians(angle))
                painter.drawLine(qt.QLineF(12 + 5*x, 12 + 5*y, 12 + 10*x, 12 + 10*y))
        else:
            painter.drawRoundedRect(qt.QRectF(2, 4, 20, 16), 1, 1)
            for x in (9, 16):
                painter.drawLine(qt.QLineF(x, 4, x, 20))
        painter.restore()

    def pixmap(self, size, mode, state):
        pixmap = qt.QPixmap(size)
        pixmap.fill(qt.Qt.GlobalColor.transparent)
        painter = qt.QPainter(pixmap)
        self.paint(painter, pixmap.rect(), mode, state)
        painter.end()
        return pixmap


class ViewModeSelector(qt.QWidget):
    currentIndexChanged = qt.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.group = qt.QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        self._index = 0
        layout.addWidget(qt.QLabel('View'))
        self.storage_controls = qt.QWidget()
        self.storage_controls.setAccessibleName('Size map views')
        storage_layout = qt.QHBoxLayout(self.storage_controls)
        storage_layout.setContentsMargins(0, 0, 0, 0)
        storage_layout.setSpacing(2)
        separator = qt.QFrame()
        separator.setFixedSize(1, 16)
        separator.setStyleSheet('background: palette(mid);')
        storage_layout.addWidget(separator)
        storage_layout.addWidget(qt.QLabel('Size Map'))
        for mode, name in ((1, 'Tiles'), (0, 'List'), (2, 'Columns'), (3, 'Treemap'), (4, 'Radial')):
            button = qt.QToolButton()
            set_painted_icon(button, ViewIcon, 5 if mode == 4 else mode)
            button.setIconSize(qt.QSize(23, 23))
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolTip(f'{name} view')
            button.setAccessibleName(f'{name} view')
            self.group.addButton(button, mode)
            self.buttons[mode] = button
            (storage_layout if mode >= 3 else layout).addWidget(button)
        self.buttons[0].setChecked(True)
        self.group.idClicked.connect(self.setCurrentIndex)

    def currentIndex(self):
        return self._index

    def currentText(self):
        return ('List', 'Tiles', 'Columns', 'Treemap', 'Radial')[self._index]

    def setCurrentIndex(self, index):
        if index not in self.buttons:
            raise ValueError('Unknown browser view')
        if not self.buttons[index].isEnabled():
            return
        self.buttons[index].setChecked(True)
        if index != self._index:
            self._index = index
            self.currentIndexChanged.emit(index)


class FolderSizeControl(qt.QWidget):
    """Inline size control; the public slider remains available to hosts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName('Icon size')
        self.setSizePolicy(qt.QSizePolicy.Policy.Fixed, qt.QSizePolicy.Policy.Fixed)
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = qt.QLabel('Size:')
        layout.addWidget(self.label)
        self.slider = qt.QSlider(qt.Qt.Orientation.Horizontal)
        self.slider.setRange(25, 100)
        self.slider.setValue(50)
        self.slider.setAccessibleName('Icon size percentage')
        self.slider.setFixedWidth(100)
        self.slider.valueChanged.connect(self._update_label)
        layout.addWidget(self.slider)
        self._update_label(50)

    def _update_label(self, percent):
        text = f'Icon size: {percent}%'
        self.slider.setToolTip(text)
        self.setToolTip(text)


def navigation_button(parent, name, icon):
    button = qt.QToolButton(parent)
    from ..reader_chrome import ReaderIcon
    icons = {qt.QStyle.StandardPixmap.SP_ArrowBack: 'previous',
             qt.QStyle.StandardPixmap.SP_ArrowForward: 'next',
             qt.QStyle.StandardPixmap.SP_ArrowUp: 'up'}
    if icon in icons:
        set_painted_icon(button, ReaderIcon, icons[icon])
    else:
        button.setIcon(parent.style().standardIcon(icon))
    button.setIconSize(qt.QSize(20, 20))
    button.setAutoRaise(True)
    button.setToolTip(name)
    button.setAccessibleName(name)
    return button
