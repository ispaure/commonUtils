"""Shared callout marker syntax for Markdown readers."""
import re

MARKER = re.compile(r'\[!(?P<kind>[\w-]+)\](?P<fold>[+-]?)(?:[ \t]+(?P<title>.*))?$')
ALIASES = {'summary': 'abstract', 'tldr': 'abstract', 'hint': 'tip', 'important': 'tip',
           'check': 'success', 'done': 'success', 'help': 'question', 'faq': 'question',
           'caution': 'warning', 'attention': 'warning', 'fail': 'failure',
           'missing': 'failure', 'error': 'danger', 'cite': 'quote'}

def callout_kind_title(match):
    kind = match['kind'].lower()
    title = match['title'] or kind.replace('-', ' ').title()
    return ALIASES.get(kind, kind), title
