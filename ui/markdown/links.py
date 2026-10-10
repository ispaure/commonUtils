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
    r'\[(?P<reference_label>[^\]\n]+)\]\[(?P<reference_target>[^\]\n]+)\]'
    r'|\[\[(?P<page>[^\]\n|]+)(?:\|(?P<alias>[^\]\n]+))?\]\]'
    r'|\[(?P<shortpage>[^\]\n|]+)\|(?P<shortalias>[^\]\n]+)\]'
    r'|\[(?P<label>[^\]\n]+)\]\((?P<url><[^>\n]+>|(?:[^()\s]|\([^()\n]*\))+)(?:[ \t]+[\"\'][^\n]*?[\"\'])?\))')


_REFERENCE = re.compile(r'^ {0,3}\[([^]\n]+)\]:[ \t]*(<[^>\n]+>|\S+)(?:[ \t]+.*)?$')


def reference_destinations(markdown):
    references = {}
    fence = None
    for line in markdown.splitlines():
        if fence:
            if fence_close(line, fence):
                fence = None
            continue
        opening = FENCE_OPEN.fullmatch(line)
        if opening:
            fence = opening.group(1)
            continue
        match = _REFERENCE.fullmatch(line)
        if match:
            key = ' '.join(match.group(1).split()).casefold()
            references.setdefault(key, match.group(2).strip('<>'))
    return references


def wiki_target(target):
    path, separator, heading = target.strip().partition('#')
    if path and not urlsplit(path).scheme and not PurePosixPath(path).suffix:
        path += '.md'
    # Encode file spaces while retaining URL schemes and fragments.
    if separator:
        heading = re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
    return quote(path, safe='/:@%?=&+') + (('#' + quote(heading, safe='%-')) if separator else '')


def link_spans(text, references=None):
    code = [(span.start, span.end) for span in inline_spans(text) if span.marker.startswith('`')]
    for match in _LINK.finditer(text):
        if any(start <= match.start() < end for start, end in code):
            continue
        if match.group('reference_target') is not None:
            label = 'reference_label'
            key = ' '.join(match.group('reference_target').split()).casefold()
            target = (references or {}).get(key)
            wiki = target is None
            if wiki:
                target = wiki_target(match.group('reference_target'))
        elif match.group('url') is not None:
            label = 'label'
            target = match.group('url').strip('<>')
            wiki = False
        else:
            label = 'alias' if match.group('alias') is not None else 'page'
            if match.group('shortpage') is not None:
                label = 'shortalias'
            target = wiki_target(match.group('page') or match.group('shortpage'))
            wiki = True
        content_start = match.start(label)
        if label == 'reference_label' and '|' in match.group(label):
            content_start += match.group(label).index('|') + 1
        yield LinkSpan(match.start(), match.end(), content_start, match.end(label), target, wiki)


def render_links(markdown):
    """Expand aliases only for preview; preserve source and literal code unchanged."""
    lines = []
    fence = None
    references = reference_destinations(markdown)
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
            for span in reversed(list(link_spans(line, references))):
                if span.wiki or re.fullmatch(r'\[[^]\n]+\]\[[^]\n]+\]', line[span.start:span.end]):
                    label = line[span.content_start:span.content_end]
                    line = line[:span.start] + '[' + label + '](' + span.target + ')' + line[span.end:]
        lines.append(line)
    return ''.join(lines)
