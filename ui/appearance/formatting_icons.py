"""Qt adapter for the same formatting vectors used by native mobile editors."""
import re
from functools import lru_cache
from .. import pyside as qt
from .formatting_glyphs import FORMATTING_PATHS


@lru_cache(maxsize=64)
def _path(source):
    tokens = iter(re.findall(r'[MLCQZ]|-?\d+(?:\.\d+)?', source))
    path = qt.QPainterPath()
    for command in tokens:
        if command == 'Z':
            path.closeSubpath()
        else:
            count = {'M': 2, 'L': 2, 'C': 6, 'Q': 4}[command]
            points = [float(next(tokens)) for _ in range(count)]
            {'M': path.moveTo, 'L': path.lineTo, 'C': path.cubicTo, 'Q': path.quadTo}[command](*points)
    return path


class FormattingIcon:
    def __init__(self, name):
        self.name = name

    def paint(self, painter, rect, mode, state):
        painter.save()
        try:
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
            painter.translate(rect.x(), rect.y())
            painter.scale(rect.width() / 24, rect.height() / 24)
            group = qt.QPalette.ColorGroup.Disabled if mode == qt.QIcon.Mode.Disabled else qt.QPalette.ColorGroup.Active
            role = (qt.QPalette.ColorRole.Highlight if state == qt.QIcon.State.On and mode != qt.QIcon.Mode.Disabled
                    else qt.QPalette.ColorRole.ButtonText)
            pen = qt.QPen(qt.QApplication.palette().color(group, role), 1.8)
            pen.setCapStyle(qt.Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(qt.Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(qt.Qt.BrushStyle.NoBrush)
            for source in FORMATTING_PATHS[self.name]:
                painter.drawPath(_path(source))
        finally:
            painter.restore()
