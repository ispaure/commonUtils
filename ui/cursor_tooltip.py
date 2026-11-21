"""A noninteractive tooltip that follows its owner's pointer without reappearing."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from . import pyside as qt


class CursorTooltip(qt.QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.label = qt.QLabel(owner, qt.Qt.WindowType.ToolTip)
        self.label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.label.setAttribute(qt.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.label.setAttribute(qt.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.label.setStyleSheet('QLabel { background: palette(toolTipBase); color: palette(toolTipText); '
                                 'border: 1px solid palette(mid); padding: 5px; }')
        owner.installEventFilter(self)

    def show(self, text, point):
        if not text:
            self.hide()
            return
        if text != self.label.text():
            self.label.setText(text)
            self.label.adjustSize()
        screen = qt.QApplication.screenAt(point) or self.owner.screen()
        bounds = screen.availableGeometry()
        position = point + qt.QPoint(16, 18)
        if position.x() + self.label.width() > bounds.right() + 1:
            position.setX(point.x() - 16 - self.label.width())
        if position.y() + self.label.height() > bounds.bottom() + 1:
            position.setY(point.y() - 18 - self.label.height())
        position.setX(max(bounds.left(), min(position.x(), bounds.right() - self.label.width() + 1)))
        position.setY(max(bounds.top(), min(position.y(), bounds.bottom() - self.label.height() + 1)))
        self.label.move(position)
        self.label.show()

    def hide(self):
        self.label.hide()

    def eventFilter(self, watched, event):
        if event.type() in (qt.QEvent.Type.Leave, qt.QEvent.Type.Hide):
            self.hide()
        return event.type() == qt.QEvent.Type.ToolTip
