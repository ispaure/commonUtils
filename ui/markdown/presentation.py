"""Palette-aware native document styling, shared by reading and rich editing.

Formats affect presentation only; custom callout interpretation is reading-only.
Keeping this out of editing/synchronization protects exact authored source.
"""
from .. import pyside as qt
from .document import space_headings
from functools import lru_cache

ACCENT = int(qt.QTextFormat.Property.UserProperty) + 701
COLORS = {'note': '#5f91ed', 'abstract': '#42a7b5', 'info': '#5f91ed', 'todo': '#5f91ed',
          'tip': '#35a58a', 'success': '#38a16b', 'question': '#bf922f', 'warning': '#cb9137',
          'failure': '#da6670', 'danger': '#da6670', 'bug': '#da6670', 'example': '#9475d5', 'quote': '#8993a2'}


@lru_cache(maxsize=1)
def monospace_family():
    # Generic "monospace" can resolve to a proportional fallback in Qt/macOS.
    # Pick an installed fixed-pitch font; no extra font download is needed.
    installed = set(qt.QFontDatabase.families())
    for family in ('Menlo', 'Cascadia Mono', 'Consolas', 'DejaVu Sans Mono', 'Liberation Mono', 'Courier New'):
        if family in installed and qt.QFontDatabase.isFixedPitch(family):
            return family
    return qt.QFontDatabase.systemFont(qt.QFontDatabase.SystemFont.FixedFont).family()


def blend(first, second, amount):
    return qt.QColor(*(round(a * (1 - amount) + b * amount) for a, b in
                      zip(first.getRgb()[:3], second.getRgb()[:3])))


def style_document(document, palette, *, callouts=None):
    """Style imported Qt Markdown without changing any characters."""
    role = qt.QPalette.ColorRole
    base, text = palette.color(role.Base), palette.color(role.Text)
    muted, accent = palette.color(role.PlaceholderText), palette.color(role.Highlight)
    alternate = blend(base, text, .035)
    document.setDocumentMargin(28)
    space_headings(document)
    active = {}
    block = document.begin()
    while block.isValid():
        cursor = qt.QTextCursor(block)
        fmt = block.blockFormat()
        depth = int(fmt.property(qt.QTextFormat.Property.BlockQuoteLevel) or 0)
        active = {level: value for level, value in active.items() if level <= depth}
        title = None
        separator = False
        iterator = block.begin()
        inline_code = []
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and fragment.charFormat().fontFixedPitch():
                inline_code.append((fragment.position(), fragment.length()))
            if fragment.isValid() and fragment.text() == '\u200b' and fragment.charFormat().anchorHref() == 'callout-end:0':
                separator = True
            if fragment.isValid() and fragment.charFormat().anchorHref().startswith('callout:'):
                try:
                    key = int(fragment.charFormat().anchorHref().split(':')[1])
                    title = (callouts or {}).get(key)
                except ValueError:
                    title = None
                if title:
                    active[depth] = title
            iterator += 1
        for position, length in inline_code:
            code_cursor = qt.QTextCursor(document)
            code_cursor.setPosition(position)
            code_cursor.setPosition(position + length, qt.QTextCursor.MoveMode.KeepAnchor)
            chars = qt.QTextCharFormat()
            chars.setFontFamilies([monospace_family()])
            chars.setBackground(alternate)
            chars.setForeground(text)
            code_cursor.mergeCharFormat(chars)
        if not fmt.headingLevel():
            fmt.setTopMargin(5)
            fmt.setBottomMargin(9)
        else:
            fmt.setBottomMargin(12)
        fmt.setLineHeight(145, qt.QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        if depth:
            callout = active.get(depth)
            color = qt.QColor(COLORS.get(callout.kind, COLORS['note'])) if callout else muted
            if base.lightness() < 128:
                color = color.lighter(120)
            fmt.setLeftMargin(18 + (depth - 1) * 20)
            fmt.setRightMargin(14)
            fmt.setBackground(blend(base, color, .1 if callout else .045))
            fmt.setProperty(ACCENT, color)
            quote_cursor = qt.QTextCursor(block)
            quote_cursor.movePosition(qt.QTextCursor.MoveOperation.EndOfBlock, qt.QTextCursor.MoveMode.KeepAnchor)
            quote_chars = qt.QTextCharFormat()
            quote_chars.setForeground(text)
            quote_cursor.mergeCharFormat(quote_chars)
            if title:
                cursor.select(qt.QTextCursor.SelectionType.BlockUnderCursor)
                chars = qt.QTextCharFormat()
                chars.setFontWeight(qt.QFont.Weight.DemiBold)
                chars.setForeground(color)
                chars.setFontUnderline(False)
                cursor.mergeCharFormat(chars)
                fmt.setTopMargin(14)
                fmt.setBottomMargin(7)
        if fmt.hasProperty(qt.QTextFormat.Property.BlockCodeLanguage) or fmt.nonBreakableLines():
            fmt.setBackground(alternate)
            fmt.setLeftMargin(14)
            fmt.setRightMargin(14)
            fmt.setLineHeight(135, qt.QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            code_cursor = qt.QTextCursor(block)
            code_cursor.movePosition(qt.QTextCursor.MoveOperation.EndOfBlock, qt.QTextCursor.MoveMode.KeepAnchor)
            chars = qt.QTextCharFormat()
            chars.setFontFamilies([monospace_family()])
            chars.setForeground(text)
            code_cursor.mergeCharFormat(chars)
        cursor.clearSelection()
        cursor.setPosition(block.position())
        if separator:
            cursor.movePosition(qt.QTextCursor.MoveOperation.EndOfBlock, qt.QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            fmt.setTopMargin(0)
            fmt.setBottomMargin(0)
            fmt.setLineHeight(3, qt.QTextBlockFormat.LineHeightTypes.FixedHeight.value)
        if cursor.currentTable() is not None:
            fmt.setTopMargin(0)
            fmt.setBottomMargin(0)
            fmt.setLineHeight(125, qt.QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor.setBlockFormat(fmt)
        block = block.next()
    for table in tables(document.rootFrame()):
        style_table(table, palette)
    if callouts is not None:
        frame_quotes(document)
        frame_code(document, alternate)
        clean_frame_boundaries(document)


def style_table(table, palette):
    """Apply the same table style during import, insertion and row/column edits."""
    role = qt.QPalette.ColorRole
    base, text = palette.color(role.Base), palette.color(role.Text)
    accent = palette.color(role.Highlight)
    alternate, border = blend(base, text, .035), blend(base, text, .16)
    fmt = table.format()
    fmt.setBorder(0)
    fmt.setCellSpacing(0)
    fmt.setCellPadding(10)
    fmt.setHeaderRowCount(1)
    fmt.setTopMargin(12)
    fmt.setBottomMargin(18)
    table.setFormat(fmt)
    for row in range(table.rows()):
        for column in range(table.columns()):
            cell = table.cellAt(row, column)
            cell_fmt = cell.format().toTableCellFormat()
            cell_fmt.setBackground(blend(base, accent, .1) if row == 0 else alternate if row % 2 else base)
            cell_fmt.setForeground(text)
            cell_fmt.setBorder(0)
            cell_fmt.setBottomBorder(1)
            cell_fmt.setBottomBorderStyle(qt.QTextFrameFormat.BorderStyle.BorderStyle_Solid)
            cell_fmt.setBottomBorderBrush(border)
            cell.setFormat(cell_fmt)


def frame_quotes(document):
    """Wrap each reading-mode quote group in a continuous, padded native card."""
    groups = []
    block = document.begin()
    while block.isValid():
        if not block.blockFormat().property(qt.QTextFormat.Property.BlockQuoteLevel):
            block = block.next()
            continue
        first = block
        while block.next().isValid() and block.next().blockFormat().property(qt.QTextFormat.Property.BlockQuoteLevel):
            block = block.next()
        groups.append((first.position(), block.position() + block.length() - 1,
                       first.blockFormat().background(), first.blockFormat().property(ACCENT)))
        block = block.next()
    for start, end, background, accent in reversed(groups):
        cursor = qt.QTextCursor(document)
        cursor.setPosition(start)
        cursor.setPosition(end, qt.QTextCursor.MoveMode.KeepAnchor)
        fmt = qt.QTextFrameFormat()
        fmt.setBackground(background)
        fmt.setBorder(0)
        fmt.setPadding(14)
        fmt.setTopMargin(12)
        fmt.setBottomMargin(12)
        fmt.setLeftMargin(4)
        fmt.setRightMargin(4)
        fmt.setProperty(ACCENT, accent)
        frame = cursor.insertFrame(fmt)
        block = document.findBlock(frame.firstPosition())
        while block.isValid() and block.position() <= frame.lastPosition():
            block_fmt = block.blockFormat()
            depth = int(block_fmt.property(qt.QTextFormat.Property.BlockQuoteLevel) or 1)
            block_fmt.setLeftMargin((depth - 1) * 20)
            block_fmt.setRightMargin(0)
            block_fmt.setTopMargin(0 if block.position() == frame.firstPosition() else 4)
            block_fmt.setBottomMargin(5)
            if depth == 1:
                block_fmt.clearBackground()
                block_fmt.clearProperty(ACCENT)
            qt.QTextCursor(block).setBlockFormat(block_fmt)
            block = block.next()



def frame_code(document, background):
    groups = []
    block = document.begin()
    while block.isValid():
        fmt = block.blockFormat()
        if not fmt.nonBreakableLines() or qt.QTextCursor(block).currentTable() is not None:
            block = block.next()
            continue
        first, language = block, fmt.property(qt.QTextFormat.Property.BlockCodeLanguage)
        while block.next().isValid() and block.next().blockFormat().nonBreakableLines() and \
                block.next().blockFormat().property(qt.QTextFormat.Property.BlockCodeLanguage) == language:
            block = block.next()
        groups.append((first.position(), block.position() + block.length() - 1))
        block = block.next()
    for start, end in reversed(groups):
        cursor = qt.QTextCursor(document)
        cursor.setPosition(start)
        cursor.setPosition(end, qt.QTextCursor.MoveMode.KeepAnchor)
        fmt = qt.QTextFrameFormat()
        fmt.setBackground(background)
        fmt.setBorder(0)
        fmt.setPadding(14)
        fmt.setTopMargin(10)
        fmt.setBottomMargin(14)
        frame = cursor.insertFrame(fmt)
        block = document.findBlock(frame.firstPosition())
        while block.isValid() and block.position() <= frame.lastPosition():
            block_fmt = block.blockFormat()
            block_fmt.clearBackground()
            block_fmt.setLeftMargin(0)
            block_fmt.setRightMargin(0)
            block_fmt.setTopMargin(0)
            block_fmt.setBottomMargin(0)
            qt.QTextCursor(block).setBlockFormat(block_fmt)
            block = block.next()


def clean_frame_boundaries(document):
    # Qt inserts empty boundary blocks when wrapping a selection in a frame.
    # Those blocks can inherit the quote/code style; keep them unobtrusive.
    block = document.begin()
    while block.isValid():
        if not block.text() and qt.QTextCursor(block).currentFrame() is document.rootFrame():
            fmt = qt.QTextBlockFormat()
            fmt.setLineHeight(2, qt.QTextBlockFormat.LineHeightTypes.FixedHeight.value)
            qt.QTextCursor(block).setBlockFormat(fmt)
        block = block.next()


def tables(frame):
    for child in frame.childFrames():
        if isinstance(child, qt.QTextTable):
            yield child
        yield from tables(child)


class MarkdownBrowser(qt.QTextBrowser):
    """Native selectable text with slim quote/callout accent rules."""
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = qt.QPainter(self.viewport())
        layout = self.document().documentLayout()
        for frame in self.document().rootFrame().childFrames():
            color = frame.format().property(ACCENT)
            if color is not None:
                rect = layout.frameBoundingRect(frame).translated(-self.horizontalScrollBar().value(),
                                                                 -self.verticalScrollBar().value())
                painter.fillRect(qt.QRectF(rect.left(), rect.top(), 3, rect.height()), color)
        # Find the first visible block; don't traverse thousands of hidden lines.
        block = self.cursorForPosition(qt.QPoint(0, 0)).block()
        while block.isValid():
            rect = layout.blockBoundingRect(block).translated(-self.horizontalScrollBar().value(),
                                                             -self.verticalScrollBar().value())
            if rect.top() > self.viewport().height():
                break
            color = block.blockFormat().property(ACCENT)
            if color is not None:
                painter.fillRect(qt.QRectF(rect.left() - 10, rect.top(), 3, rect.height()), color)
            block = block.next()
        painter.end()


def configure_text(widget, *, source=False):
    modified = widget.document().isModified()
    font = qt.QFontDatabase.systemFont(qt.QFontDatabase.SystemFont.FixedFont if source else
                                     qt.QFontDatabase.SystemFont.GeneralFont)
    font.setPointSizeF(12 if source else 13)
    if source:
        font.setFamily(monospace_family())
    widget.setFont(font)
    widget.setFrameShape(qt.QFrame.Shape.NoFrame)
    widget.document().setDocumentMargin(28)
    widget.setTabStopDistance(qt.QFontMetricsF(font).horizontalAdvance(' ') * 4)
    widget.document().setModified(modified)
