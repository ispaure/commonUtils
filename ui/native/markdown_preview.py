"""Bounded offline Markdown, with escaped HTML and no external resources."""
from html import escape
import re
from urllib.parse import quote, urlsplit

from markdown_it import MarkdownIt

_ALIAS = re.compile(r'\[\[([^]\n|]+)\|([^]\n]+)\]\]|\[([^]\n|]+)\|([^]\n]+)\]')


def _alias(state, silent):
    """Recognize existing wiki aliases through the parser, outside code spans."""
    if state.src[state.pos] != '[' or state.linkLevel:
        return False
    match = _ALIAS.match(state.src, state.pos, state.posMax)
    if not match:
        return False
    if not silent:
        token = state.push('link_open', 'a', 1)
        token.attrSet('href', quote((match[1] or match[3]).strip(), safe='/:@%#?=&+'))
        token = state.push('text', '', 0)
        token.content = match[2] or match[4]
        state.push('link_close', 'a', -1)
    state.pos = match.end()
    return True


def markdown_body(text, *, local_links=False):
    """Render CommonMark with tables/strikethrough and opt-in local wiki links.

    HTML is escaped, images show their alt text and external links remain inert.
    The pure-Python parser is shared by all native hosts, including chat.
    """
    if len(text.encode('utf-8')) > 1024 * 1024:
        raise ValueError('Preview is limited to 1 MiB.')
    parser = MarkdownIt('commonmark', {'html': False, 'maxNesting': 32}).enable(['table', 'strikethrough'])
    parser.inline.ruler.before('link', 'wiki_alias', _alias)
    tokens = parser.parse(text)
    headings = set()
    heading_counts = {}

    def prepare(items):
        links = []
        for index, token in enumerate(items):
            if token.type == 'heading_open':
                content = items[index + 1]
                title = ''.join(child.content for child in content.children or []
                                if child.type in ('text', 'code_inline', 'image'))
                slug = re.sub(r'[^\w\s-]', '', title).strip().lower()
                slug = re.sub(r'\s+', '-', slug)
                count = heading_counts.get(slug, 0)
                anchor = slug + (f'-{count}' if count else '')
                while anchor in headings:
                    count += 1
                    anchor = f'{slug}-{count}'
                heading_counts[slug] = count + 1
                headings.add(anchor)
                token.attrSet('id', anchor)
            elif token.type == 'link_open':
                target = token.attrGet('href') or ''
                try:
                    parsed = urlsplit(target)
                    allowed = (local_links and not parsed.scheme and not parsed.netloc
                               and not target.startswith(('/', '\\'))
                               and not any(ord(char) < 32 for char in target))
                except ValueError:
                    allowed = False
                links.append(bool(allowed))
                if not allowed:
                    token.tag = 'span'
                    token.attrs = {}
            elif token.type == 'link_close':
                if not links.pop():
                    token.tag = 'span'
            if token.children:
                prepare(token.children)
    prepare(tokens)

    def image(renderer, items, index, options, env):
        return '<span class="image-alt">' + escape(renderer.renderInlineAsText(items[index].children or [], options, env)) + '</span>'

    def table_open(renderer, items, index, options, env):
        return '<div class="table-scroll" role="region" aria-label="Table" tabindex="0"><table>\n'

    def table_close(renderer, items, index, options, env):
        return '</table></div>\n'

    for name, rule in (('image', image),
                       ('table_open', table_open), ('table_close', table_close)):
        parser.add_render_rule(name, rule)
    return parser.renderer.render(tokens, parser.options, {})


def markdown_preview(text, font_size=16, *, local_links=False, stylesheet=""):
    size = int(font_size)
    if not 12 <= size <= 32:
        raise ValueError('Invalid preview font size.')
    body = markdown_body(text, local_links=local_links)
    policy = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    result = ('<!doctype html><html><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="{policy}">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<style>:root{{color-scheme:light dark;--surface:Canvas;--text:CanvasText}}{stylesheet}body{{background:var(--surface);color:var(--text);font: {size}px/1.6 system-ui;margin:16px;overflow-wrap:anywhere}}'
            'h1,h2,h3,h4,h5,h6{line-height:1.25;margin:1.4em 0 .6em}h1{font-size:1.8em}h2{font-size:1.45em}h3{font-size:1.2em}'
            'body>:first-child{margin-top:0}p{margin:.65em 0}ul,ol{padding-left:1.5em;margin:.6em 0}li>p{margin:.25em 0}li>ul,li>ol{margin:.25em 0}'
            'a{color:var(--accent,LinkText);text-decoration:underline}blockquote{margin:1em 0;padding:.1em 1em;border-left:3px solid GrayText}'
            'hr{border:0;border-top:1px solid GrayText;margin:1.4em 0}pre{white-space:pre;overflow-x:auto;padding:.8em;border:1px solid GrayText;border-radius:8px}'
            'code{font-family:monospace}p code,li code,td code{background:color-mix(in srgb,currentColor 8%,transparent);padding:.1em .25em;border-radius:4px}'
            '.table-scroll{max-width:100%;overflow-x:auto;margin:1em 0}table{border-collapse:collapse;width:100%;font-size:.95em}'
            'th,td{border:1px solid GrayText;padding:.55em .7em;min-width:6em;vertical-align:top}th{font-weight:600;background:color-mix(in srgb,currentColor 8%,transparent)}'
            '</style></head><body>' + body + '</body></html>')
    if len(result.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('The rendered preview exceeds 2 MiB; preview a smaller document.')
    return result
