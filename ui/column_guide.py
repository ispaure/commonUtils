"""Optional visual column boundary for plain-text source editors."""

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


class ColumnGuide:
    column_guide = 0

    def set_column_guide(self, column):
        """Show a visual column boundary; zero disables it without changing text."""
        if type(column) is not int or not 0 <= column <= 1000:
            raise ValueError('Column guide must be an integer between 0 and 1000')
        self.column_guide = column
        self.viewport().update()

    def column_guide_x(self):
        return (self.contentOffset().x() + self.document().documentMargin()
                + qt.QFontMetricsF(self.font()).horizontalAdvance(' ') * self.column_guide)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.column_guide:
            with qt.QPainter(self.viewport()) as painter:
                color = self.palette().color(qt.QPalette.ColorRole.Mid)
                painter.setPen(qt.QPen(color, 1, qt.Qt.PenStyle.DashLine))
                x = self.column_guide_x()
                painter.drawLine(qt.QLineF(x, 0, x, self.viewport().height()))

