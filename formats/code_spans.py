"""Bounded Pygments colour spans and UTF-16 line positions for native editors."""
from .code_syntax import detect_language, syntax_style

MAX_HIGHLIGHT_CHARS = 128 * 1024
MAX_SPANS = 20000


def line_offsets(text):
    """Logical line starts in UTF-16 units (the native text APIs' coordinates)."""
    starts, offset = [0], 0
    for char in text:
        offset += 2 if ord(char) > 0xffff else 1
        if char == '\n':
            starts.append(offset)
    return starts


def syntax_spans(text, filename='', *, language=None, dark=False):
    """Return (language, [(UTF16 start, end, RGB), ...]); never execute source.

    Large documents retain plain editing and line numbers. Lexer whitespace is
    preserved, including trailing newlines, so spans never refer to synthetic text.
    """
    language = language or detect_language(filename, text)
    if language == 'text' or len(text) > MAX_HIGHLIGHT_CHARS:
        return language, []
    from pygments.lexers import get_lexer_by_name
    try:
        if language == 'blade':
            from .code_blade import BladeLexer
            lexer = BladeLexer(stripnl=False, ensurenl=False)
        else:
            lexer = get_lexer_by_name(language, stripnl=False, ensurenl=False)
    except ValueError:
        return 'text', []
    style = syntax_style(dark)
    positions = [0]
    for char in text:
        positions.append(positions[-1] + (2 if ord(char) > 0xffff else 1))
    spans = []
    colours = {}
    for index, kind, value in lexer.get_tokens_unprocessed(text):
        if kind not in colours:
            ancestor = kind
            while True:
                try:
                    colours[kind] = style.style_for_token(ancestor)['color']
                    break
                except KeyError:
                    ancestor = ancestor.parent
                    if ancestor is None:
                        colours[kind] = None
                        break
        colour = colours[kind]
        if colour and index < len(text) and value:
            spans.append((positions[index], positions[min(len(text), index + len(value))], int(colour, 16)))
            if len(spans) > MAX_SPANS:
                return language, []
    return language, spans
