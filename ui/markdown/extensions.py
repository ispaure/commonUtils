"""Reading-only extensions. Authored Markdown is never rewritten by a preview.

Obsidian callouts use normal block quotes; only their title is translated to an
internal link. Fences are tracked so examples and diagram sources stay literal.
"""
from dataclasses import dataclass
import re

QUOTE_PREFIX = re.compile(r'^(?: {0,3}>[ \t]?)+')
CALLOUT = re.compile(r'^(?P<quote>(?: {0,3}>[ \t]?)+)\s*\[!(?P<kind>[\w-]+)\](?P<fold>[+-]?)(?:\s+(?P<title>.*))?$', re.I)
FENCE = re.compile(r'^\s{0,3}(`{3,}|~{3,})(.*)$')
ALIASES = {'summary': 'abstract', 'tldr': 'abstract', 'hint': 'tip', 'important': 'tip',
           'check': 'success', 'done': 'success', 'help': 'question', 'faq': 'question',
           'caution': 'warning', 'attention': 'warning', 'fail': 'failure',
           'missing': 'failure', 'error': 'danger', 'cite': 'quote'}


@dataclass(frozen=True)
class Callout:
    key: int
    kind: str
    title: str
    depth: int
    foldable: bool
    collapsed: bool


def reading_source(source, folded=None):
    """Return Markdown suitable for Qt and callout descriptors keyed by line.

    + starts expanded, - starts collapsed; titles act as fold links. Nested
    callouts are supported, including hiding descendants with their parent.
    """
    folded = folded or {}
    lines, result, callouts = source.splitlines(), [], {}
    fence = None
    fence_depth = 0
    hidden_depth = None
    open_callout = False
    for number, line in enumerate(lines):
        quote_prefix = QUOTE_PREFIX.match(line)
        depth = quote_prefix[0].count('>') if quote_prefix else 0
        if fence and depth < fence_depth:
            fence = None
        if hidden_depth is not None:
            if depth >= hidden_depth:
                continue
            hidden_depth = None
        if not depth and open_callout and not fence:
            # Qt merges adjacent quotes even across a blank line. A disposable
            # root-level anchor marks the end so ordinary quotes don't inherit
            # the previous callout's color or fold state.
            result.extend(['', '[\u200b](callout-end:0)', ''])
            open_callout = False
        # Remove quote prefixes only for fence detection (nested code examples).
        content = line[quote_prefix.end():] if quote_prefix else line
        match_fence = FENCE.match(content)
        if fence:
            result.append(line)
            if match_fence and match_fence[1][0] == fence[0] and len(match_fence[1]) >= len(fence) and not match_fence[2].strip():
                fence = None
            continue
        if match_fence:
            fence = match_fence[1]
            fence_depth = depth
            result.append(line)
            continue
        match = CALLOUT.match(line)
        if not match:
            result.append(line)
            continue
        kind = match['kind'].lower()
        title = match['title'] or kind.replace('-', ' ').title()
        foldable = bool(match['fold'])
        collapsed = foldable and folded.get(number, match['fold'] == '-')
        callouts[number] = Callout(number, ALIASES.get(kind, kind), title, depth, foldable, collapsed)
        open_callout = True
        label = ('▸ ' if collapsed else '▾ ') + title if foldable else title
        # Escape link syntax while allowing authored emphasis in the title.
        label = label.replace('[', '\\[').replace(']', '\\]')
        quote = '> ' * depth
        result.extend([quote + f'[{label}](callout:{number})', quote.rstrip()])
        if collapsed:
            hidden_depth = depth
    if open_callout:
        result.extend(['', '[\u200b](callout-end:0)'])
    return '\n'.join(result), callouts


def mermaid_blocks(source):
    """Extract complete, unquoted Mermaid fences; ignore nested/other fences."""
    blocks, fence, start, language = [], None, 0, ''
    lines = source.splitlines()
    for number, line in enumerate(lines):
        match = FENCE.match(line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                if language == 'mermaid':
                    blocks.append((start, number, '\n'.join(lines[start + 1:number])))
                fence = None
        elif match:
            fence, start, language = match[1], number, match[2].strip().lower()
    return blocks
