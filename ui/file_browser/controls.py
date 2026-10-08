"""Scalable, palette-aware icons and compact browser view controls."""

from .. import pyside as qt


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
        if self.mode == 1:
            for x in (3, 13):
                for y in (3, 13):
                    painter.drawRoundedRect(qt.QRectF(x, y, 7, 7), 1, 1)
        elif self.mode == 0:
            for y in (5, 12, 19):
                painter.drawEllipse(qt.QPointF(4, y), .8, .8)
                painter.drawLine(qt.QLineF(9, y, 21, y))
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
        for mode, name in ((1, 'Tiles'), (0, 'List'), (2, 'Columns')):
            button = qt.QToolButton()
            button.setIcon(qt.QIcon(ViewIcon(mode)))
            button.setIconSize(qt.QSize(23, 23))
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolTip(f'{name} view')
            button.setAccessibleName(f'{name} view')
            self.group.addButton(button, mode)
            self.buttons[mode] = button
            layout.addWidget(button)
        self.buttons[0].setChecked(True)
        self.group.idClicked.connect(self.setCurrentIndex)

    def currentIndex(self):
        return self._index

    def currentText(self):
        return ('List', 'Tiles', 'Columns')[self._index]

    def setCurrentIndex(self, index):
        if index not in self.buttons:
            raise ValueError('Unknown browser view')
        self.buttons[index].setChecked(True)
        if index != self._index:
            self._index = index
            self.currentIndexChanged.emit(index)


class FolderSizeControl(qt.QToolButton):
    """Tile-only size menu; the owner connects slider.valueChanged to its view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText('Size')
        self.setAccessibleName('Icon size')
        self.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = qt.QMenu(self)
        widget = qt.QWidget()
        layout = qt.QVBoxLayout(widget)
        self.label = qt.QLabel()
        layout.addWidget(self.label)
        self.slider = qt.QSlider(qt.Qt.Orientation.Horizontal)
        self.slider.setRange(25, 100)
        self.slider.setValue(50)
        self.slider.setAccessibleName('Icon size percentage')
        self.slider.valueChanged.connect(self._update_label)
        layout.addWidget(self.slider)
        action = qt.QWidgetAction(menu)
        action.setDefaultWidget(widget)
        menu.addAction(action)
        self.setMenu(menu)
        self._update_label(50)

    def _update_label(self, percent):
        text = f'Icon size: {percent}%'
        self.label.setText(text)
        self.setToolTip(text)


def navigation_button(parent, name, icon):
    button = qt.QToolButton(parent)
    button.setIcon(parent.style().standardIcon(icon))
    button.setIconSize(qt.QSize(20, 20))
    button.setAutoRaise(True)
    button.setToolTip(name)
    button.setAccessibleName(name)
    return button
