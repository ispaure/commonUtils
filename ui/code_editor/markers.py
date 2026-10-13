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
    changes = []
    for tag, a, b, c, d in SequenceMatcher(None, before.splitlines(keepends=True),
            after.splitlines(keepends=True), autojunk=True).get_opcodes():
        if tag == 'equal':
            continue
        if tag == 'replace':
            # A replacement can also remove/add whole lines. Pair the common
            # span as modifications and retain the surplus as a distinct marker.
            paired = min(b - a, d - c)
            changes.append(LineChange('modify', a, a + paired, c, c + paired))
            if b - a > paired:
                changes.append(LineChange('delete', a + paired, b, d, d))
            elif d - c > paired:
                changes.append(LineChange('add', b, b, c + paired, d))
        else:
            changes.append(LineChange({'insert': 'add', 'delete': 'delete'}[tag], a, b, c, d))
    return tuple(changes)
