"""Folder trails, theme-aware chevrons, and a matching selected-file preview column."""

from .. import pyside as qt
from .editing import FilenameEditorMixin


class ColumnDelegate(FilenameEditorMixin, qt.QStyledItemDelegate):
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
    column_context_requested = qt.Signal(object, object)
    def __init__(self):
        super().__init__()
        self.setIconSize(qt.QSize(16, 16))
        self.viewport().setBackgroundRole(qt.QPalette.ColorRole.Window)
        self.viewport().setAutoFillBackground(True)
        self.preview_container = qt.QWidget()
        self.preview_layout = qt.QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.setPreviewWidget(self.preview_container)
        self.preview_host = self.preview_container.parentWidget().parentWidget()
        self.preview_host.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_host.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.preview_host.viewport().installEventFilter(self)
        self.set_file_preview_visible(False)

    def eventFilter(self, watched, event):
        if event.type() == qt.QEvent.Type.Resize:
            if watched is self.preview_host.viewport():
                self.preview_container.setMinimumHeight(max(0, watched.height()))
            elif not self.preview_container.isHidden():
                qt.QTimer.singleShot(0, self, self._sync_preview_width)
        return super().eventFilter(watched, event)

    def _sync_preview_width(self):
        if not self.preview_container.isHidden():
            self.set_file_preview_visible(True)

    def setColumnWidths(self, widths):
        super().setColumnWidths(widths)
        self._sync_preview_width()

    def set_file_preview_visible(self, visible):
        widths = self.columnWidths()
        depth = 0
        parent = self.currentIndex().parent()
        while parent.isValid() and parent != self.rootIndex():
            depth += 1
            parent = parent.parent()
        width = widths[min(depth, len(widths)-1)] if widths else 240
        if hasattr(self, 'setPreviewColumnVisible'):
            self.setPreviewColumnVisible(visible)
        # Qt before 6.11 has no public visibility switch for the preview host.
        self.preview_host.setFixedWidth(width if visible else 0)
        self.preview_container.setFixedWidth(width if visible else 0)
        self.preview_container.setMinimumHeight(self.preview_host.viewport().height() if visible else 0)
        self.preview_container.setVisible(visible)

    def setIconSize(self, size):
        super().setIconSize(size)
        for column in self.findChildren(qt.QListView):
            column.setIconSize(size)

    def createColumn(self, index):
        column = super().createColumn(index)
        column.setItemDelegate(ColumnDelegate(column))
        column.setEditTriggers(qt.QAbstractItemView.EditTrigger.SelectedClicked | qt.QAbstractItemView.EditTrigger.EditKeyPressed)
        column.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        column.customContextMenuRequested.connect(lambda point, target=column: self.column_context_requested.emit(target, point))
        column.setIconSize(self.iconSize())
        column.installEventFilter(self)
        column.viewport().installEventFilter(self)
        column.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        return column
