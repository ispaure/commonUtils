"""Reveal actions for Qt password and token fields."""
from .. import pyside as qt


class EyeIcon(qt.QIconEngine):
    def __init__(self, revealed=False):
        super().__init__()
        self.revealed = revealed

    def clone(self):
        return EyeIcon(self.revealed)

    def paint(self, painter, rect, mode, state):
        painter.save()
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        painter.translate(rect.x(), rect.y())
        painter.scale(rect.width() / 24, rect.height() / 24)
        group = qt.QPalette.ColorGroup.Disabled if mode == qt.QIcon.Mode.Disabled else qt.QPalette.ColorGroup.Active
        painter.setPen(qt.QPen(qt.QApplication.palette().color(group, qt.QPalette.ColorRole.Text), 1.8))
        painter.setBrush(qt.Qt.BrushStyle.NoBrush)
        path = qt.QPainterPath(qt.QPointF(2, 12))
        path.cubicTo(7, 3, 17, 3, 22, 12)
        path.cubicTo(17, 21, 7, 21, 2, 12)
        painter.drawPath(path)
        painter.drawEllipse(qt.QPointF(12, 12), 3, 3)
        if self.revealed:
            painter.drawLine(qt.QLineF(4, 3, 20, 21))
        painter.restore()

    def pixmap(self, size, mode, state):
        pixmap = qt.QPixmap(size)
        pixmap.fill(qt.Qt.GlobalColor.transparent)
        painter = qt.QPainter(pixmap)
        try:
            self.paint(painter, pixmap.rect(), mode, state)
        finally:
            painter.end()
        return pixmap


def password_field(field):
    """Mask an existing QLineEdit and attach an accessible trailing eye action."""
    if hasattr(field, 'visibility_action'):
        return field
    field.setEchoMode(qt.QLineEdit.EchoMode.Password)
    action = field.addAction(qt.QIcon(EyeIcon()), qt.QLineEdit.ActionPosition.TrailingPosition)
    action.setText('Show password')
    action.setToolTip('Show password')
    action.setCheckable(True)
    field.visibility_action = action

    def reveal(visible):
        field.setEchoMode(qt.QLineEdit.EchoMode.Normal if visible else qt.QLineEdit.EchoMode.Password)
        label = 'Hide password' if visible else 'Show password'
        action.setText(label)
        action.setToolTip(label)
        action.setIcon(qt.QIcon(EyeIcon(visible)))

    action.toggled.connect(reveal)
    field.textChanged.connect(lambda text: action.setChecked(False) if not text else None)
    return field
