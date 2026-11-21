"""CommonMark rules for portable Markdown readers and speech preparation."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

import re
from urllib.parse import quote, unquote, urlsplit

from .images import wiki_image

ALIAS = re.compile(r'\[\[([^]\n|]+)(?:\|([^]\n]+))?\]\]|\[([^]\n|]+)\|([^]\n]+)\]')
EMBED = re.compile(r'!\[\[([^]\n|]+)(?:\|([^]\n]+))?\]\]')
TASK = re.compile(r'^\[([ xX])\][ \t]+')
HIDDEN_FENCES = frozenset({'dataview', 'dataviewjs'})
FOOTNOTE_DEFINITION = re.compile(r'\[\^([^]\s]+)\]:[ \t]*(.*)')
FOOTNOTE_REFERENCE = re.compile(r'\[\^([^]\s]+)\]')
ASSET = re.compile(r'\.(?:avif|bmp|gif|heic|ico|jpe?g|png|svg|tiff?|webp|m4v|mov|mp4|webm)$', re.I)


def code_language(token):
    return (token.info.strip().split(maxsplit=1) or [''])[0].casefold()


def markdown_parser(*, wiki_images=False):
    """Configure the offline Markdown parser without importing any UI toolkit."""
    from markdown_it import MarkdownIt

    parser = MarkdownIt('commonmark', {'html': False, 'maxNesting': 32}).enable(['table', 'strikethrough'])
    parser.inline.ruler.before('link', 'wiki_alias', _wiki_alias)
    parser.inline.ruler.before('image', 'wiki_embed', _wiki_embed if wiki_images else _wiki_note)
    parser.inline.ruler.before('html_inline', 'hidden_comment', _inline_comment)
    parser.block.ruler.before('html_block', 'hidden_comment', _block_comment, {'alt': ['paragraph', 'blockquote']})
    parser.block.ruler.before('reference', 'footnote', _footnote, {'alt': ['paragraph']})
    parser.inline.ruler.before('link', 'footnote_reference', _footnote_reference)
    parser.inline.ruler.before('escape', 'math', _inline_math)
    parser.block.ruler.before('paragraph', 'math', _block_math, {'alt': ['paragraph']})
    return parser


def _wiki_alias(state, silent):
    """Recognize wiki aliases through the parser, outside code spans."""
    if (state.src[state.pos] != '[' or state.linkLevel
            or (state.pos and state.src[state.pos - 1] in '![')):
        return False
    match = ALIAS.match(state.src, state.pos, state.posMax)
    if not match:
        return False
    if not silent:
        target = (match[1] or match[3]).strip()
        label = 2 if match[2] is not None else 4 if match[4] is not None else 1
        _link(state, target, match, label)
    state.pos = match.end()
    return True


def _link(state, target, match, label):
    token = state.push('link_open', 'a', 1)
    token.attrSet('href', quote(target.strip(), safe='/:@%#?=&+'))
    token = state.push('text', '', 0)
    token.content = match[label]
    token.meta['label_span'] = match.span(label)
    state.push('link_close', 'a', -1)


def asset_embed(target):
    try:
        return bool(ASSET.search(unquote(target).strip()) or ASSET.search(unquote(urlsplit(target).path)))
    except ValueError:
        return False


def _wiki_note(state, silent):
    match = EMBED.match(state.src, state.pos, state.posMax)
    if not match or asset_embed(match[1]):
        return False
    if not silent:
        _link(state, match[1], match, 2 if match[2] is not None else 1)
    state.pos = match.end()
    return True


def _wiki_embed(state, silent):
    return _wiki_note(state, silent) or wiki_image(state, silent)


def _comment(text, start):
    if text.startswith('<!--', start):
        return '<!--', '-->'
    if text.startswith('%%', start):
        return '%%', '%%'
    return '', ''


def _inline_comment(state, silent):
    opening, closing = _comment(state.src, state.pos)
    if not opening:
        return False
    end = state.src.find(closing, state.pos + len(opening), state.posMax)
    if end < 0:
        return False
    if not silent:
        state.push('hidden_comment', '', 0)
    state.pos = end + len(closing)
    return True


def _block_comment(state, first, last, silent):
    if state.is_code_block(first):
        return False
    start = state.bMarks[first] + state.tShift[first]
    opening, closing = _comment(state.src, start)
    if not opening:
        return False
    end_line = None
    for line in range(first, last):
        begin = start + len(opening) if line == first else state.bMarks[line]
        end = state.src.find(closing, begin, state.eMarks[line])
        if end >= 0:
            if state.src[end + len(closing):state.eMarks[line]].strip():
                return False
            end_line = line + 1
            break
    if end_line is None:
        if opening != '<!--':
            return False
        end_line = last
    if not silent:
        token = state.push('hidden_comment', '', 0)
        token.map = [first, end_line]
        state.line = end_line
    return True


def _footnote(state, first, last, silent):
    if state.is_code_block(first):
        return False
    begin = state.bMarks[first] + state.tShift[first]
    match = FOOTNOTE_DEFINITION.fullmatch(state.src[begin:state.eMarks[first]])
    if not match:
        return False
    if silent:
        return True
    key = match[1].casefold()
    known = state.env.setdefault('footnotes', set())
    end = first + 1
    # Continuations use four spaces relative to the surrounding container.
    while end < last and state.sCount[end] - state.blkIndent >= 4:
        end += 1
    state.line = end
    if key in known:
        return True
    known.add(key)
    token = state.push('footnote_open', 'aside', 1)
    token.attrSet('class', 'markdown-footnote')
    token.map = [first, end]
    token.meta['prefix'] = (begin, begin + match.start(2))
    token = state.push('inline', '', 0)
    token.map = [first, end]
    token.content = '\n'.join([match[2], *(state.src[state.bMarks[line] + state.tShift[line]:
                                                   state.eMarks[line]] for line in range(first + 1, end))])
    token.children = []
    state.push('footnote_close', 'aside', -1)
    return True


def _footnote_reference(state, silent):
    match = FOOTNOTE_REFERENCE.match(state.src, state.pos, state.posMax)
    if not match or match[1].casefold() not in state.env.get('footnotes', ()):
        return False
    if not silent:
        token = state.push('footnote_reference', 'sup', 0)
        token.content = match[1]
    state.pos = match.end()
    return True


def _inline_math(state, silent):
    start = state.pos
    if state.src[start] != '$' or start + 1 >= state.posMax or state.src[start + 1].isspace():
        return False
    marker = '$$' if state.src.startswith('$$', start) else '$'
    match = re.compile(r'(?<![\\$])' + re.escape(marker) + r'(?![\d$])').search(
        state.src, start + len(marker), state.posMax)
    if not match or state.src[match.start() - 1].isspace() or '\n' in state.src[start:match.start()]:
        return False
    if not silent:
        token = state.push('math_source', 'span', 0)
        token.content = state.src[start:match.end()]
    state.pos = match.end()
    return True


def _block_math(state, first, last, silent):
    if state.is_code_block(first):
        return False
    begin = state.bMarks[first] + state.tShift[first]
    if state.src[begin:state.eMarks[first]].strip() != '$$':
        return False
    for line in range(first + 1, last):
        begin = state.bMarks[line] + state.tShift[line]
        if state.src[begin:state.eMarks[line]].strip() == '$$':
            if not silent:
                token = state.push('math_source', 'pre', 0)
                token.content = state.getLines(first, line + 1, state.blkIndent, False)
                token.map = [first, line + 1]
                state.line = line + 1
            return True
    return False
