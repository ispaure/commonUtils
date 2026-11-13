"""Qt's visible Markdown runs and UTF-16 coordinates for read-aloud."""
from ...formats.markdown.speech import RenderedRun, prepare_rendered, reading_markup
from ...formats.markdown.tokens import HIDDEN_FENCES
from ...runtime.speech_text import utf16_length
from .. import pyside as qt
from .presentation import CODE_LANGUAGE

_MATH = int(qt.QTextFormat.Property.UserProperty) + 710
_FOOTNOTE = _MATH + 1


def prepare_document(widget, *, selection=True):
    """Snapshot the visible Qt document or its current selection."""
    cursor = widget.textCursor()
    if selection and cursor.hasSelection():
        start, end = cursor.selectionStart(), cursor.selectionEnd()
    else:
        start, end = 0, widget.document().characterCount() - 1
    return prepare_rendered(_runs(widget.document(), start, end))


def _runs(document, start, end):
    block = document.findBlock(start)
    previous_cell = None
    previous_code = None
    while block.isValid() and block.position() < end:
        cursor = qt.QTextCursor(block)
        table = cursor.currentTable()
        frame = cursor.currentFrame()
        cell = table.cellAt(cursor) if table is not None else None
        location = (table, cell.row(), cell.column()) if cell is not None else None
        fmt = block.blockFormat()
        language = fmt.property(qt.QTextFormat.Property.BlockCodeLanguage) or frame.frameFormat().property(CODE_LANGUAGE)
        language = (str(language or '').split(maxsplit=1) or [''])[0].casefold()
        code = frame if language or fmt.nonBreakableLines() else None
        if block.isVisible() and language not in HIDDEN_FENCES:
            boundary = 'block'
            if location is not None:
                boundary = ('row' if previous_cell is None or previous_cell[:2] != location[:2]
                            else 'cell' if previous_cell != location else 'line')
            elif code is not None and previous_code is code:
                boundary = 'line'
            cue = ''
            if block.textList() is not None:
                marker = fmt.marker()
                if marker == qt.QTextBlockFormat.MarkerType.Checked:
                    cue = 'checked'
                elif marker == qt.QTextBlockFormat.MarkerType.Unchecked:
                    cue = 'unchecked'
            yield from _fragments(block, start, end, boundary, cue)
            previous_cell, previous_code = location, code
        block = block.next()


def _fragments(block, start, end, boundary, cue):
    fragment = block.begin()
    while not fragment.atEnd():
        item = fragment.fragment()
        fragment += 1
        if not item.isValid() or item.charFormat().isImageFormat():
            continue
        position = item.position()
        text = item.text()
        href = item.charFormat().anchorHref()
        if item.charFormat().property(_FOOTNOTE):
            cue = 'Footnote'
            continue
        if item.charFormat().property(_MATH) or href == 'callout-end:0':
            continue
        if href.startswith('callout:') and text.startswith(('▸ ', '▾ ')):
            text, position = text[2:], position + 2
        left, right = max(position, start), min(position + utf16_length(text), end)
        if right <= left:
            continue
        text = text.encode('utf-16-le')[(left - position) * 2:(right - position) * 2].decode('utf-16-le', errors='replace')
        for line in text.replace('\u2028', '\n').split('\n'):
            if line:
                yield RenderedRun(line, left, boundary, cue)
                cue = ''
            left += utf16_length(line) + 1
            boundary = 'line'
        boundary = ''



def protect_markup(markdown):
    """Remove hidden metadata and retain tokens for Qt's visible speech roles."""
    markdown = markdown.replace('\r\n', '\n').replace('\r', '\n')
    spans = reading_markup(markdown)
    prefix = 'zzspeechmarkup'
    while prefix in markdown:
        prefix += 'z'
    tokens = {}
    for left, right, kind in reversed(spans):
        value = markdown[left:right]
        if kind == 'hidden':
            replacement = '\n' * value.count('\n')
        else:
            key = f'{prefix}{len(tokens)}z'
            replacement = key + '\n' * value.count('\n')
            tokens[key] = (kind, value.rstrip('\n') if kind == 'math' else '\u200b')
        markdown = markdown[:left] + replacement + markdown[right:]
    return markdown, tokens


def restore_markup(document, tokens):
    for key, (kind, value) in tokens.items():
        cursor = document.find(key)
        if not cursor.isNull():
            fmt = cursor.charFormat()
            fmt.setProperty(_MATH if kind == 'math' else _FOOTNOTE, True)
            cursor.insertText(value, fmt)
