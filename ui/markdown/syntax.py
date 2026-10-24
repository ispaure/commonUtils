"""Shared inline/fence parsing for live display and Markdown export."""
from ...formats.markdown.editing import (InlineSpan, inline_spans, FENCE_OPEN, HEADING, fence_close)
from .. import pyside as qt


def _units(text):
    """Qt cursor positions count UTF-16 units rather than Python code points."""
    return len(text.encode('utf-16-le')) // 2


def fenced_regions(document):
    """Yield opening block, optional closing block, marker and language, excluding tables."""
    opening = None
    block = document.begin()
    while block.isValid():
        if qt.QTextCursor(block).currentTable() is not None:
            if opening:
                # An unfinished fence must not flatten an existing rich table
                # during export. Stop its editable range before the table frame.
                yield opening[0], block.previous(), opening[1], opening[2]
                opening = None
            block = block.next()
            continue
        if block.blockFormat().nonBreakableLines():
            block = block.next()
            continue
        text = block.text()
        if opening is None:
            match = FENCE_OPEN.fullmatch(text)
            if match:
                opening = (block, match.group(1), match.group(2).strip())
        elif fence_close(text, opening[1]):
            yield opening[0], block, opening[1], opening[2]
            opening = None
        block = block.next()
    if opening:
        yield opening[0], None, opening[1], opening[2]
