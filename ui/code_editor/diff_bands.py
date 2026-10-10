"""Shared palette-aware unified diff bands and dual line-number gutter."""
from .. import pyside as qt
from .widget import CodeEdit


def diff_colors(palette, kind):
    dark = palette.base().color().lightness() < 128
    return ({'add': ('#76dfae', '#204c3d'), 'remove': ('#ff9caa', '#582d39'),
             'hunk': ('#a6cfff', '#2d3d56')} if dark else
            {'add': ('#17643d', '#d8f2e1'), 'remove': ('#a32238', '#fce0e4'),
             'hunk': ('#235a91', '#e0ebf8')})[kind]


class DiffEdit(CodeEdit):
    """Keep the shared editor, with old/new line numbers and visible diff bands."""
    def __init__(self):
        super().__init__()
        self.diff_rows = []
        self._bands_key = None
        self.updateRequest.connect(self._refresh_bands)

    def _refresh_bands(self, *args):
        if self.diff_rows: self.highlight_cursor()

    def setPlainText(self, text):
        # The shared cursor handler runs before our textChanged handler.
        self.diff_rows = []
        self._bands_key = None
        super().setPlainText(text)

        self.update_gutter()
        self.gutter.setFixedWidth(self.gutter_width())

    def set_diff(self, view, *, raw=False):
        self.setPlainText(view.raw_text if raw else view.text)
        lines = view.raw_lines if raw else view.lines
        self.diff_rows = [(line.old, line.new, line.kind) for line in lines]
        self._update_diff_gutter()

    def _update_diff_gutter(self):
        self._bands_key = None
        self.update_gutter()
        self.gutter.setFixedWidth(self.gutter_width())
        self.highlight_cursor()

    def gutter_width(self):
        if not getattr(self, 'diff_rows', None): return super().gutter_width()
        digits = max(len(row[0]) for row in self.diff_rows) + max(len(row[1]) for row in self.diff_rows)
        return self.fontMetrics().horizontalAdvance('9') * digits + 24

    def paint_gutter(self, event):
        if not self.diff_rows: return super().paint_gutter(event)
        painter = qt.QPainter(self.gutter)
        painter.fillRect(event.rect(), self.palette().alternateBase())
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        half = self.gutter.width() // 2
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                old, new, kind = self.diff_rows[block.blockNumber()]
                if kind in ('add', 'remove', 'hunk'):
                    painter.fillRect(0, top, self.gutter.width(), height,
                                     qt.QColor(diff_colors(self.palette(), kind)[1]))
                painter.setPen(self.palette().color(qt.QPalette.ColorRole.PlaceholderText))
                for x, number in ((0, old), (half, new)):
                    painter.drawText(x, top, half - 5, height, qt.Qt.AlignmentFlag.AlignRight, number)
            top += height
            block = block.next()

    def highlight_cursor(self, *args):
        if not getattr(self, 'diff_rows', None): return super().highlight_cursor()
        block = self.firstVisibleBlock()
        key = (block.blockNumber(), self.viewport().size().width(), self.viewport().height(), self.font().key(),
               self.palette().cacheKey(), id(self.search_selections))
        if key == self._bands_key: return
        self._bands_key = key
        selections = []
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        while block.isValid() and top <= self.viewport().height():
            kind = self.diff_rows[block.blockNumber()][2]
            if kind in ('add', 'remove', 'hunk'):
                selection = qt.QTextEdit.ExtraSelection()
                selection.format.setBackground(qt.QColor(diff_colors(self.palette(), kind)[1]))
                selection.format.setProperty(qt.QTextFormat.Property.FullWidthSelection, True)
                selection.cursor = qt.QTextCursor(block)
                selections.append(selection)
            top += self.blockBoundingRect(block).height()
            block = block.next()
        self.setExtraSelections(selections + self.search_selections)
        self.gutter.update()


class DiffHighlighter(qt.QSyntaxHighlighter):
    def __init__(self, editor):
        super().__init__(editor.document())
        self.editor = editor

    def highlightBlock(self, text):
        rows = self.editor.diff_rows
        index = self.currentBlock().blockNumber()
        kind = rows[index][2] if index < len(rows) else None
        if kind in ('hunk', 'add', 'remove'):
            form = qt.QTextCharFormat()
            form.setForeground(qt.QColor(diff_colors(self.editor.palette(), kind)[0]))
            if kind == 'hunk': form.setFontWeight(qt.QFont.Weight.Bold)
            self.setFormat(0, len(text), form)


