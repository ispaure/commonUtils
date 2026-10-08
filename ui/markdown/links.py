"""Local wiki aliases and Markdown links shared by reading, editing and export."""
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit
import re
from .syntax import inline_spans, FENCE_OPEN, fence_close


@dataclass(frozen=True)
class LinkSpan:
    start: int
    end: int
    content_start: int
    content_end: int
    target: str
    wiki: bool = False


# Angle-bracket destinations and balanced parentheses cover typical file/URL links.
_LINK = re.compile(r'(?<![\\!\[])(?:'
    r'\[\[(?P<page>[^\]\n|]+)(?:\|(?P<alias>[^\]\n]+))?\]\]'
    r'|\[(?P<shortpage>[^\]\n|]+)\|(?P<shortalias>[^\]\n]+)\]'
    r'|\[(?P<label>[^\]\n]+)\]\((?P<url><[^>\n]+>|(?:[^()\s]|\([^()\n]*\))+)(?:[ \t]+[\"\'][^\n]*?[\"\'])?\))')


def wiki_target(target):
    path, separator, heading = target.strip().partition('#')
    if path and not urlsplit(path).scheme and not PurePosixPath(path).suffix:
        path += '.md'
    # Encode file spaces while retaining URL schemes and fragments.
    if separator:
        heading = re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
    return quote(path, safe='/:@%?=&+') + (('#' + quote(heading, safe='%-')) if separator else '')


def link_spans(text):
    code = [(span.start, span.end) for span in inline_spans(text) if span.marker.startswith('`')]
    for match in _LINK.finditer(text):
        if any(start <= match.start() < end for start, end in code):
            continue
        if match.group('url') is not None:
            label = 'label'
            target = match.group('url').strip('<>')
            wiki = False
        else:
            label = 'alias' if match.group('alias') is not None else 'page'
            if match.group('shortpage') is not None:
                label = 'shortalias'
            target = wiki_target(match.group('page') or match.group('shortpage'))
            wiki = True
        yield LinkSpan(match.start(), match.end(), match.start(label), match.end(label), target, wiki)


def render_links(markdown):
    """Expand aliases only for preview; preserve source and literal code unchanged."""
    lines = []
    fence = None
    for line in markdown.splitlines(keepends=True):
        opening = FENCE_OPEN.fullmatch(line.rstrip('\r\n'))
        if fence:
            lines.append(line)
            if fence_close(line.rstrip('\r\n'), fence):
                fence = None
            continue
        if opening:
            fence = opening.group(1)
        else:
            for span in reversed(list(link_spans(line))):
                if span.wiki:
                    label = line[span.content_start:span.content_end]
                    line = line[:span.start] + '[' + label + '](' + span.target + ')' + line[span.end:]
        lines.append(line)
    return ''.join(lines)
