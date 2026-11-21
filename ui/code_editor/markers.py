"""Host-supplied line changes; no filesystem or Git dependencies."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

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
