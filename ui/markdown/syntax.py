"""Shared inline/fence parsing for live display and Markdown export."""
from dataclasses import dataclass
import re
from .. import pyside as qt


def _units(text):
    """Qt cursor positions count UTF-16 units rather than Python code points."""
    return len(text.encode('utf-16-le')) // 2


@dataclass(frozen=True)
class InlineSpan:
    start: int
    end: int
    marker: str
    body: str

    @property
    def content_start(self):
        return self.start + len(self.marker)

    @property
    def content_end(self):
        return self.end - len(self.marker)


_INLINE = (
    re.compile(r'(?<![\\`])(?P<marker>`{1,2})(?!`)(?P<body>.+?)(?P=marker)(?!`)'),
    re.compile(r'(?<![\\*])(?P<marker>\*{3})(?!\*)(?=\S)(?P<body>.+?)(?<=\S)(?<!\\)(?P=marker)(?!\*)'),
    re.compile(r'(?<![\\\w_])(?P<marker>_{3})(?!_)(?=\S)(?P<body>.+?)(?<=\S)(?<!\\)(?P=marker)(?![\w_])'),
    re.compile(r'(?<![\\*])(?P<marker>\*{2})(?!\*)(?=\S)(?P<body>.+?)(?<=\S)(?<!\\)(?P=marker)(?!\*)'),
    re.compile(r'(?<![\\\w_])(?P<marker>_{2})(?!_)(?=\S)(?P<body>.+?)(?<=\S)(?<!\\)(?P=marker)(?![\w_])'),
    re.compile(r'(?<![\\*])(?P<marker>\*)(?!\*)(?=\S)(?P<body>.+?)(?<=\S)(?<!\\)(?P=marker)(?!\*)'),
    re.compile(r'(?<![\\\w_])(?P<marker>_)(?!_)(?=\S)(?P<body>.+?)(?<=\S)(?<!\\)(?P=marker)(?![\w_])'),
)
FENCE_OPEN = re.compile(r'^ {0,3}(`{3,}|~{3,})([^`\n]*)$')
HEADING = re.compile(r'^(#{1,6}) ')


def inline_spans(text):
    """Find supported spans, including nested emphasis, but never parse code payloads."""
    spans = []
    code = []
    for pattern in _INLINE:
        for match in pattern.finditer(text):
            if any(start <= match.start() < end for start, end in code):
                continue
            if not match.group('marker').startswith('`'):
                prefix = text[:match.start()]
                if len(re.findall(r'(?<![\\`])`(?!`)', prefix)) % 2:
                    continue
            span = InlineSpan(match.start(), match.end(), match.group('marker'), match.group('body'))
            spans.append(span)
            if span.marker.startswith('`'):
                code.append((span.start, span.end))
    return sorted(spans, key=lambda span: (span.start, -span.end))


def fence_close(text, marker):
    return re.fullmatch(r' {0,3}' + re.escape(marker[0]) + '{' + str(len(marker)) + r',}\s*', text) is not None


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
