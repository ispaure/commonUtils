"""Obsidian-compatible image size hints shared by desktop and native renderers."""
import re

_SIZE = re.compile(r'([1-9][0-9]{0,5})(?:x([1-9][0-9]{0,5}))?\Z')


def image_size(label):
    """Return (caption, width, height); invalid hints remain literal alt text."""
    caption, separator, size = label.rpartition('|')
    match = _SIZE.fullmatch((size if separator else label).strip())
    if match is None:
        return label, None, None
    return (caption if separator else '', int(match[1]), int(match[2]) if match[2] else None)


def wiki_image(state, silent):
    """Opt-in wiki/pasted embeds; code spans and escaped bangs stay literal."""
    if escaped_image(state, silent):
        return True
    if not state.src.startswith('![[', state.pos):
        return False
    end = state.src.find(']]', state.pos + 3, state.posMax)
    if end < 0 or '\n' in state.src[state.pos:end]:
        return False
    content = state.src[state.pos + 3:end]
    target, _, alt = content.partition('|')
    if not target.strip():
        return False
    if not silent:
        from markdown_it.token import Token
        from urllib.parse import quote
        token = state.push('image', 'img', 0)
        token.attrSet('src', quote(target.strip(), safe='/:%'))
        token.meta['wiki_source'] = state.src[state.pos:end + 2]
        token.content = (target.strip() + '|' + alt) if image_size(alt)[1] is not None else (alt or target.strip())
        child = Token('text', '', 0)
        child.content = token.content
        token.children = [child]
    state.pos = end + 2
    return True


def escaped_image(state, silent):
    """Accept pasted image syntax with an escaped opening parenthesis.

    Delegate destination/title validation to CommonMark, and retain the exact
    source for formatted editors. An escaped exclamation mark stays literal.
    """
    from markdown_it.rules_inline.image import image
    start = state.pos
    if not state.src.startswith('![', start):
        return False
    end = state.md.helpers.parseLinkLabel(state, start + 1, False)
    if end < 0 or not state.src.startswith('\\(', end + 1):
        return False
    original, maximum = state.src, state.posMax
    state.src = original[:end + 1] + original[end + 2:]
    state.posMax -= 1
    try:
        accepted = image(state, silent)
        if accepted:
            state.pos += 1
            if not silent:
                state.tokens[-1].meta['wiki_source'] = original[start:state.pos]
        return accepted
    finally:
        state.src, state.posMax = original, maximum



def image_targets(text):
    """Collect parsed Markdown/wiki image destinations, excluding code and escapes."""
    from markdown_it import MarkdownIt
    parser = MarkdownIt('commonmark', {'html': False}).enable(['table', 'strikethrough'])
    parser.inline.ruler.before('image', 'wiki_image', wiki_image)
    def targets(tokens):
        for token in tokens:
            if token.type == 'image':
                yield token.attrGet('src') or ''
            elif token.children:
                yield from targets(token.children)
    return tuple(dict.fromkeys(targets(parser.parse(text))))
