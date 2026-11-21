"""Prepare already-authorized Markdown or rendered runs for the speech session."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import re

from ...runtime.speech_text import has_content, utf16_length
from .callouts import MARKER, callout_kind_title
from .properties import split_frontmatter


@dataclass(frozen=True, slots=True)
class RenderedRun:
    """Visible text with its UTF-16 start and optional boundary or spoken cue.

    A cue is synthesized before the visible text, whose source range anchors it.
    Boundary values are `line`, `cell`, `row` and `block`.
    """

    text: str
    start: int | None = None
    boundary: str = ''
    cue: str = ''
    end: int | None = None


_BOUNDARIES = {'': '', 'cell': ' ', 'line': '\n', 'row': '\n\n', 'block': '\n\n'}
_PRIORITY = {name: number for number, name in enumerate(_BOUNDARIES)}
_INVISIBLE = str.maketrans({'\u200b': ' ', '\ufffc': ' ', '\u2028': '\n', '\u2029': '\n'})


@dataclass(frozen=True, slots=True)
class _Span:
    first: int
    last: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class PreparedSpeech:
    text: str
    breaks: tuple[int, ...]
    _spans: tuple[_Span, ...]
    _speech_ends: tuple[int, ...]
    _source_ends: tuple[int, ...]
    _source_starts: tuple[int, ...]

    def source_range(self, start, end):
        """Return a UTF-16 highlight range, or None when no source is mapped."""
        if start < 0 or start >= end:
            return None
        left = bisect_right(self._speech_ends, start)
        selected = []
        for index in range(left, len(self._spans)):
            span = self._spans[index]
            if span.first >= end:
                break
            if span.last - span.first == span.end - span.start:
                selected.append((span.start + max(0, start - span.first),
                                 span.end - max(0, span.last - end)))
            else:
                selected.append((span.start, span.end))
        if selected:
            return min(first for first, _ in selected), max(last for _, last in selected)
        return None

    def speech_position(self, source_position):
        """Map a source location to speech, advancing across hidden markup."""
        index = bisect_right(self._source_ends, source_position)
        if index >= len(self._spans):
            return utf16_length(self.text)
        at_start = bisect_left(self._source_starts, source_position)
        if at_start < len(self._spans) and self._source_starts[at_start] == source_position:
            return self._spans[at_start].first
        span = self._spans[index]
        if span.start < source_position and span.last - span.first != span.end - span.start and index + 1 < len(self._spans):
            following = self._spans[index + 1]
            if following.start == span.start and following.end >= source_position:
                span = following
        if span.last - span.first == span.end - span.start:
            return span.first + max(0, source_position - span.start)
        return span.first


def prepare_rendered(runs):
    """Convert visible runs to a speech payload and keep their coordinate map."""
    parts, breaks, spans = [], [], []
    offset = 0
    boundary = ''
    for run in runs:
        if _PRIORITY[run.boundary] > _PRIORITY[boundary]:
            boundary = run.boundary
        value = run.text.translate(_INVISIBLE)
        if not run.cue and (not value or boundary and not value.strip()):
            continue
        if boundary and parts:
            breaks.append(offset)
            separator = _BOUNDARIES[boundary]
            parts.append(separator)
            offset += len(separator)
        boundary = ''
        width = utf16_length(value)
        end = run.end if run.end is not None else (run.start + width if run.start is not None else None)
        if run.cue:
            cue = run.cue + ' '
            cue_width = utf16_length(cue)
            if run.start is not None and end > run.start:
                # Anchor a spoken cue to the first visible word.
                first_word = re.search(r'\S+', value)
                cue_end = min(end, run.start + utf16_length(value[:first_word.end()])) if first_word else end
                spans.append(_Span(offset, offset + cue_width, run.start, cue_end))
            parts.append(cue)
            offset += cue_width
        if width and run.start is not None and end > run.start:
            spans.append(_Span(offset, offset + width, run.start, end))
        parts.append(value)
        offset += width
    text = ''.join(parts)
    if not has_content(text):
        return PreparedSpeech('', (), (), (), (), ())
    # A synthesized cue and its anchor can overlap in source space.
    source_ends = []
    for span in spans:
        source_ends.append(max(span.end, source_ends[-1] if source_ends else 0))
    return PreparedSpeech(text, tuple(breaks), tuple(spans),
                          tuple(span.last for span in spans), tuple(source_ends),
                          tuple(span.start for span in spans))


def _units(text):
    result = [0]
    for char in text:
        result.append(result[-1] + (2 if ord(char) > 0xffff else 1))
    return result


class _Source:
    """Locate parser fragments inside their original lines, retaining UTF-16."""

    def __init__(self, body, base):
        self.body = body
        self.lines = [0] + [match.end() for match in re.finditer('\n', body)]
        self.units = _units(body)
        self.base = base
        self.cursor = 0

    def locate(self, value, first, last):
        if not value:
            return ()
        begin = self.lines[first] if first < len(self.lines) else len(self.body)
        limit = self.lines[last] if last < len(self.lines) else len(self.body)
        cursor = max(begin, self.cursor)
        spans = []
        lines = value.split('\n')
        for number, piece in enumerate(lines):
            if piece:
                point = self.body.find(piece, cursor, limit)
                if point < 0:
                    # GFM table cells remove the backslash before an escaped pipe.
                    escaped = piece.replace('|', '\\|')
                    point = self.body.find(escaped, cursor, limit)
                    if point >= 0:
                        for char in piece:
                            left = point + int(char == '|')
                            spans.append((self.base + self.units[left], self.base + self.units[left + 1]))
                            point = left + 1
                        cursor = point
                    else:
                        spans.extend([None] * len(piece))
                else:
                    spans.extend((self.base + self.units[i], self.base + self.units[i + 1])
                                 for i in range(point, point + len(piece)))
                    cursor = point + len(piece)
            if number + 1 < len(lines):
                newline = self.body.find('\n', cursor, limit)
                if newline < 0:
                    spans.append(None)
                else:
                    spans.append((self.base + self.units[newline], self.base + self.units[newline + 1]))
                    cursor = newline + 1
        self.cursor = cursor
        return spans


def _mapped(value, positions, first, last, boundary='', cue=''):
    selected = positions[first:last]
    exact = len(value) == len(selected) and all(selected)
    if exact and selected:
        start, end = selected[0]
        index = 0
        for next_index, (left, right) in enumerate(selected[1:], 1):
            if end != left:
                yield RenderedRun(value[index:next_index], start, boundary, cue, end)
                index, start, boundary, cue = next_index, left, '', ''
            end = right
        yield RenderedRun(value[index:], start, boundary, cue, end)
        return
    known = [span for span in selected if span]
    yield RenderedRun(value, known[0][0] if known else None, boundary, cue, known[-1][1] if known else None)


def _tracked_parser():
    """Retain inline token spans through markdown-it's delimiter resolution."""
    from .tokens import markdown_parser
    from markdown_it.rules_inline import StateInline

    parser = markdown_parser(wiki_images=True)
    parser.disable('text_join')
    parser.inline.ruler2.disable('fragments_join')

    class SourceState(StateInline):
        def pushPending(self):
            value = self.pending
            # Link parsing moves the cursor to its label before flushing the
            # previous token. Newline handling can trim pending whitespace.
            lower = getattr(self, 'pending_start', self.pos)
            start = self.src.find(value, lower, self.pos)
            token = super().pushPending()
            if start >= 0:
                token.meta['span'] = (start, start + len(value))
            self.pending_start = self.pos
            return token

        def push(self, *args):
            token = super().push(*args)
            if args[0] == 'link_open':
                self.pending_start = self.pos
            return token

    def track(rule):
        def tracked(state, silent):
            if silent:
                return rule(state, silent)
            start = state.pos
            had_pending = bool(state.pending)
            if not had_pending:
                state.pending_start = start
            before = len(state.tokens)
            if not rule(state, silent):
                return False
            tokens = state.tokens[before:]
            for token in tokens:
                token.meta.setdefault('span', (start, state.pos))
            # Unmatched delimiter runs are literal individual characters.
            if tokens and all(token.type == 'text' and token.content for token in tokens):
                position = start
                for token in tokens:
                    if token.meta['span'] == (start, state.pos):
                        found = state.src.find(token.content, position, state.pos)
                        if found >= 0:
                            position = found + len(token.content)
                            token.meta['span'] = (found, position)
            return True
        return tracked

    for name, rule in zip(parser.inline.ruler.get_active_rules(), parser.inline.ruler.getRules('')):
        parser.inline.ruler.at(name, track(rule))

    def parse_inline(src, md, env, tokens):
        state = SourceState(src, md, env, tokens)
        parser.inline.tokenize(state)
        for rule in parser.inline.ruler2.getRules(''):
            rule(state)
        return state.tokens

    parser.inline.parse = parse_inline
    return parser


def _inline(children, positions, boundary='', cue=''):
    for token in children:
        if token.type in {'hardbreak', 'softbreak'}:
            if token.type == 'hardbreak':
                boundary = 'line'
            else:
                yield RenderedRun(' ', boundary=boundary)
                boundary = ''
            continue
        if token.type not in {'text', 'text_special', 'code_inline'}:
            continue
        if not token.content:
            continue
        start, end = token.meta.get('label_span', token.meta.get('span', (0, 0)))
        if token.type == 'code_inline':
            start += len(token.markup)
            end -= len(token.markup)
            if end - start == len(token.content) + 2:
                start += 1
                end -= 1
        if token.type == 'text_special' and token.info == 'escape' and end - start == len(token.content) + 1:
            start += 1
        yield from _mapped(token.content, positions, start, end, boundary, cue)
        boundary = cue = ''


def _markdown_runs(parser, source):
    from .tokens import code_language, HIDDEN_FENCES, TASK

    tokens = parser.parse(source.body)
    boundary, cue, collapsed = '', '', None
    tasks = []
    for index, token in enumerate(tokens):
        kind = token.type
        if collapsed is not None:
            if kind != 'blockquote_close' or token.level != collapsed:
                continue
            collapsed = None
        if kind == 'blockquote_open' and tokens[index + 1].type == 'paragraph_open':
            inline = tokens[index + 2]
            line, _, rest = inline.content.partition('\n')
            match = MARKER.fullmatch(line)
            if match:
                _, title = callout_kind_title(match)
                positions = source.locate(inline.content, *inline.map)
                children = parser.parseInline(title)[0].children
                title_positions = positions[match.start('title'):match.end('title')] if match['title'] else ()
                yield from _inline(children, title_positions, 'block')
                inline.meta['callout_body'] = rest
                inline.meta['callout_positions'] = positions[len(line) + 1:]
                if match['fold'] == '-':
                    collapsed = token.level
                boundary = 'block'
                continue
        if kind == 'list_item_open':
            tasks.append(True)
        elif kind == 'list_item_close':
            tasks.pop()
        elif kind == 'footnote_open':
            boundary, cue = 'block', 'Footnote'
        elif kind in {'tr_open', 'tr_close'}:
            boundary = 'row'
        elif kind in {'th_close', 'td_close'}:
            boundary = 'cell'
        elif kind in {'heading_open', 'heading_close', 'paragraph_open', 'paragraph_close',
                      'blockquote_open', 'blockquote_close', 'list_item_open', 'list_item_close'}:
            boundary = 'block'

        if kind == 'inline':
            value = token.meta.get('callout_body', token.content)
            positions = token.meta.get('callout_positions')
            children = token.children
            if positions is None:
                positions = source.locate(value, *token.map)
            else:
                children = parser.parseInline(value)[0].children
            if tasks and tasks[-1]:
                tasks[-1] = False
                task = TASK.match(value)
                if task:
                    cue = 'checked' if task[1].lower() == 'x' else 'unchecked'
                    value = value[task.end():]
                    positions = positions[task.end():]
                    children = parser.parseInline(value)[0].children
            yield from _inline(children, positions, boundary, cue)
            boundary = cue = ''
        elif kind in {'code_block', 'fence'}:
            if code_language(token) in HIDDEN_FENCES:
                continue
            first, last = token.map
            start_line = first + int(kind == 'fence')
            positions = source.locate(token.content, start_line, last)
            offset = 0
            for line in token.content.rstrip('\n').split('\n'):
                yield from _mapped(line, positions, offset, offset + len(line), 'block' if not offset else 'line')
                offset += len(line) + 1
            boundary = 'block'


def prepare_markdown(markdown):
    """Prepare authored Markdown without loading images, embeds or generated views.

    Source ranges refer to the original Markdown. A host can instead supply
    already-rendered, authorized output via `prepare_rendered`.
    """
    text = markdown.removeprefix('\ufeff')
    parts = split_frontmatter(text)
    base = utf16_length(parts.prefix) + len(markdown) - len(text)
    normalized = re.sub(r'\r\n?|\x00', lambda m: '\ufffd' if m[0] == '\x00' else '\n', parts.body)
    source = _Source(normalized, base)
    if '\r' in parts.body:
        source.units = [0]
        for match in re.finditer(r'\r\n|[\s\S]', parts.body):
            source.units.append(source.units[-1] + utf16_length(match[0]))
    return prepare_rendered(_markdown_runs(_tracked_parser(), source))


def reading_markup(markdown):
    """Find hidden comments, note cues and literal math in a Qt reading source.

    Results use Python string indexes. Qt receives the rendered text via its
    native importer, so readers can continue selecting and navigating that view.
    """
    if not any(marker in markdown for marker in ('<!--', '%%', '[^', '$')):
        return ()
    try:
        parser = _tracked_parser()
    except ImportError:
        return ()

    # Markdown-it normalizes line endings before parsing. Match its offsets.
    source = _Source(markdown, 0)
    source.units = list(range(len(markdown) + 1))
    spans = []
    for token in parser.parse(markdown):
        if token.type in {'hidden_comment', 'math_source'} and token.map is not None:
            start, end = token.map
            left = source.lines[start]
            right = source.lines[end] if end < len(source.lines) else len(markdown)
            spans.append((left, right, 'math' if token.type == 'math_source' else 'hidden'))
        elif token.type == 'footnote_open':
            left, right = token.meta['prefix']
            spans.append((left, right, 'footnote'))
        elif token.type == 'inline' and token.map is not None:
            positions = source.locate(token.content, *token.map)
            for child in token.children:
                if child.type not in {'hidden_comment', 'math_source', 'footnote_reference'}:
                    continue
                left, right = child.meta.get('span', (0, 0))
                if left < right <= len(positions) and positions[left] and positions[right - 1]:
                    spans.append((positions[left][0], positions[right - 1][1],
                                  'math' if child.type == 'math_source' else 'hidden'))
    return tuple(sorted(spans))
