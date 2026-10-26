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
    """Opt-in image embeds; code spans and escaped syntax stay literal."""
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
