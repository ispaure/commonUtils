"""Folder-only column trails with compact, theme-aware chevrons."""

from .. import pyside as qt


class ColumnDelegate(qt.QStyledItemDelegate):
    arrow_size = 8

    def paint(self, painter, option, index):
        option = qt.QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        rtl = option.direction == qt.Qt.LayoutDirection.RightToLeft
        has_children = index.model().hasChildren(index)
        style = option.widget.style() if option.widget else qt.QApplication.style()
        style.drawPrimitive(qt.QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)
        rect = qt.QRect(option.rect)
        margin = self.arrow_size + 10
        option.rect.adjust(margin if rtl else 0, 0, 0 if rtl else -margin, 0)
        super().paint(painter, option, index)
        if has_children:
            x = rect.left() + margin / 2 if rtl else rect.right() - margin / 2
            y = rect.center().y()
            color = option.palette.color(qt.QPalette.ColorRole.HighlightedText if option.state & qt.QStyle.StateFlag.State_Selected
                                         else qt.QPalette.ColorRole.Text)
            painter.save()
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
            painter.setPen(qt.QPen(color, 1.2))
            half = self.arrow_size / 2
            direction = -1 if rtl else 1
            painter.drawLine(qt.QLineF(x - direction * half / 2, y - half, x + direction * half / 2, y))
            painter.drawLine(qt.QLineF(x + direction * half / 2, y, x - direction * half / 2, y + half))
            painter.restore()


class FolderColumnView(qt.QColumnView):
    def __init__(self):
        super().__init__()
        self.viewport().setBackgroundRole(qt.QPalette.ColorRole.Window)
        self.viewport().setAutoFillBackground(True)
        if hasattr(self, 'setPreviewColumnVisible'):
            self.setPreviewColumnVisible(False)
        else:
            # Before Qt 6.11, the public preview widget still needs a zero-width host.
            preview = qt.QWidget()
            preview.setFixedWidth(0)
            self.setPreviewWidget(preview)
            host = preview.parentWidget().parentWidget()
            host.setFixedWidth(0)
            host.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            host.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def createColumn(self, index):
        column = super().createColumn(index)
        column.setItemDelegate(ColumnDelegate(column))
        column.setIconSize(qt.QSize(16, 16))
        column.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        return column
