"""Cursor-sensitive Markdown display; highlighting never changes text or undo history."""
from .. import pyside as qt
from .syntax import inline_spans, FENCE_OPEN, fence_close, HEADING, fenced_regions
from .syntax import _units
from .links import link_spans


class LivePreviewHighlighter(qt.QSyntaxHighlighter):
    def __init__(self, editor):
        super().__init__(editor.document())
        self.editor = editor
        self._refreshing = False
        self._active_fence_blocks = set()

    def refresh_cursor(self):
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self._active_fence_blocks = set()
            for opening, closing, _, _ in fenced_regions(self.editor.document()):
                end = closing.position() + _units(closing.text()) if closing else self.editor.document().characterCount()
                if self._active(opening.position(), end):
                    last = closing.blockNumber() if closing else self.editor.document().lastBlock().blockNumber()
                    self._active_fence_blocks.update(range(opening.blockNumber(), last + 1))
            self.rehighlight()
        finally:
            self._refreshing = False

    def _active(self, start, end):
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            return cursor.selectionStart() < end and cursor.selectionEnd() > start
        return start <= cursor.position() < end

    def _marker_format(self, active, *, collapse=False):
        fmt = qt.QTextCharFormat()
        fmt.setFontWeight(qt.QFont.Weight.Normal)
        fmt.setFontItalic(False)
        fmt.setFontFixedPitch(False)
        if active:
            fmt.setForeground(self.editor.palette().color(qt.QPalette.ColorRole.PlaceholderText))
        elif collapse:
            # Qt ignores sub-point sizes on some platforms. A one-pixel font
            # with negative tracking clamps every marker advance to zero.
            font = qt.QFont(self.editor.font())
            font.setPixelSize(1)
            font.setLetterSpacing(qt.QFont.SpacingType.AbsoluteSpacing, -1)
            fmt.setFont(font)
            fmt.setForeground(qt.QColor('transparent'))
        else:
            fmt.setFontPointSize(0.1)
            fmt.setForeground(qt.QColor('transparent'))
        return fmt

    def highlightBlock(self, text):
        block = self.currentBlock()
        position = block.position()
        state = self.previousBlockState()
        in_table = qt.QTextCursor(block).currentTable() is not None
        if in_table:
            state = 0
        opening = FENCE_OPEN.fullmatch(text) if state < 1 and not in_table else None
        if state >= 1 or opening:
            code = qt.QTextCharFormat()
            code.setFontFixedPitch(True)
            code.setFontFamilies(['monospace'])
            code.setFontWeight(qt.QFont.Weight.Normal)
            code.setFontItalic(False)
            self.setFormat(0, _units(text), code)
            if opening:
                marker = opening.group(1)
                self.setCurrentBlockState(len(marker) * 2 + (marker[0] == '~'))
            else:
                marker = ('~' if state % 2 else '`') * (state // 2)
                self.setCurrentBlockState(0 if fence_close(text, marker) else state)
            if opening or (state >= 1 and fence_close(text, marker)):
                self.setFormat(0, _units(text), self._marker_format(block.blockNumber() in self._active_fence_blocks))
            return
        self.setCurrentBlockState(0)
        if block.blockFormat().nonBreakableLines():
            return
        heading = HEADING.match(text)
        if heading:
            self.setFormat(0, heading.end(), self._marker_format(
                self._active(position, position + _units(text) + 1), collapse=True))
        links = list(link_spans(text))
        for span in links:
            start, end = _units(text[:span.start]), _units(text[:span.end])
            first, last = _units(text[:span.content_start]), _units(text[:span.content_end])
            fmt = qt.QTextCharFormat()
            fmt.setForeground(self.editor.palette().color(qt.QPalette.ColorRole.Link))
            fmt.setFontUnderline(True)
            self.setFormat(first, last - first, fmt)
            marker = self._marker_format(self._active(position + start, position + end))
            self.setFormat(start, first - start, marker)
            self.setFormat(last, end - last, marker)
        for span in inline_spans(text):
            if any(link.start <= span.start < link.end and not
                   (link.content_start <= span.start and span.end <= link.content_end) for link in links):
                continue
            start, end = _units(text[:span.start]), _units(text[:span.end])
            first, last = _units(text[:span.content_start]), _units(text[:span.content_end])
            active = self._active(position + start, position + end)
            fmt = qt.QTextCharFormat()
            if span.marker.startswith('`'):
                fmt.setFontFixedPitch(True)
                fmt.setFontFamilies(['monospace'])
            else:
                if len(span.marker) >= 2:
                    fmt.setFontWeight(qt.QFont.Weight.Bold)
                if len(span.marker) in (1, 3):
                    fmt.setFontItalic(True)
            # Merge nested syntax styles instead of overwriting an outer bold span.
            for index in range(first, last):
                combined = self.format(index)
                combined.merge(fmt)
                self.setFormat(index, 1, combined)
            marker_fmt = self._marker_format(active)
            self.setFormat(start, first - start, marker_fmt)
            self.setFormat(last, end - last, marker_fmt)
