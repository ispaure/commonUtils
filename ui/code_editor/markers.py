"""Host-supplied line changes; no filesystem or Git dependencies."""
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class LineChange:
    kind: str
    old_start: int
    old_end: int
    start: int
    end: int


def line_changes(before, after):
    """Zero-based half-open spans; deletions anchor before start (including EOF)."""
    return tuple(LineChange({'insert': 'add', 'replace': 'modify', 'delete': 'delete'}[tag], a, b, c, d)
                 for tag, a, b, c, d in SequenceMatcher(None, before.splitlines(keepends=True),
                     after.splitlines(keepends=True), autojunk=True).get_opcodes() if tag != 'equal')
