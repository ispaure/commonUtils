"""Toolkit-free live Markdown syntax shared by Qt and WebView editors."""
from dataclasses import dataclass
import re


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
SELECTION_MARKERS = ('*', '_', '`')
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


def web_patterns():
    """Export the same patterns for JavaScript's named capture syntax."""
    def javascript(pattern):
        return re.sub(r'\(\?P=([a-z]+)\)', r'\\k<\1>',
                      pattern.replace('(?P<', '(?<').replace(r'\w', r'\p{L}\p{N}'))
    return dict(inline=[javascript(pattern.pattern) for pattern in _INLINE],
                heading=HEADING.pattern, selection=list(SELECTION_MARKERS), active=WEB_EDITING_JS)


# Kept beside the shared syntax grammar so native and web adapters use one
# visibility contract: touching caret boundaries, strictly overlapping selections.
def syntax_active(start, end, first, last):
    """Whether a source interval is being edited (all offsets in caller units)."""
    return first < end and last > start if first != last else start <= first <= end


SYNTAX_ACTIVE_JS = """function syntaxActive(start, end, first, last) {
    return first !== last ? first < end && last > start : start <= first && first <= end;
}"""


# Web adapter lives with the native parser and interval predicate. Consumers
# supply livePatterns/inlinePatterns; DOM, source and undo remain host-owned.
WEB_EDITING_JS = SYNTAX_ACTIVE_JS + r"""
function liveSpans(text) {
    const spans = [], code = [];
    for (const pattern of inlinePatterns) {
        pattern.lastIndex = 0;
        for (const match of text.matchAll(pattern)) {
            const start = match.index, end = start + match[0].length;
            if (code.some(([first, last]) => first <= start && start < last)) continue;
            const marker = match.groups.marker;
            if (!marker.startsWith('`') && (text.slice(0, start).match(/(?<![\\`])`(?!`)/g) || []).length % 2) continue;
            spans.push({start, end, marker});
            if (marker.startsWith('`')) code.push([start, end]);
        }
    }
    return spans;
}
"""
