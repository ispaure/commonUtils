"""Qt-independent three-way text merge and undoable resolution session.

Inputs are immutable; result ranges follow edits. File/Git policy belongs to callers.
Overlapping changes are grouped conservatively, including insertions at boundaries.
"""
from dataclasses import dataclass
from difflib import SequenceMatcher

MAX_CHARS = 1024 * 1024
MAX_LINES = 5000


def bounded(text):
    if len(text) > MAX_CHARS or len(text.splitlines()) > MAX_LINES:
        raise ValueError('Comparison is limited to 1 MiB of text and 5,000 lines per input.')


@dataclass(frozen=True)
class MergeRegion:
    start: int
    end: int
    base: str
    left: str
    right: str
    left_lines: tuple
    right_lines: tuple
    conflict: bool


@dataclass(frozen=True)
class MergeModel:
    base: str
    left: str
    right: str
    regions: tuple


def merge_text(base, left, right):
    for text in (base, left, right):
        bounded(text)
    source = base.splitlines(keepends=True)
    sides = [left.splitlines(keepends=True), right.splitlines(keepends=True)]
    opcodes = [SequenceMatcher(None, source, side, autojunk=False).get_opcodes() for side in sides]
    edits = sorted((i, j, side) for side, codes in enumerate(opcodes)
                   for tag, i, j, k, l in codes if tag != 'equal')
    groups = []
    for start, end, side in edits:
        if groups and (start < groups[-1][1] or
                       start == groups[-1][1] and (start == end or groups[-1][0] == groups[-1][1])):
            groups[-1][1] = max(end, groups[-1][1])
        else:
            groups.append([start, end])

    def boundary(codes, point, end=False):
        # Include insertions on the boundary, and keep replacements as a unit.
        candidates = []
        for tag, i, j, k, l in codes:
            if i <= point <= j:
                candidates.append(k + point - i if tag == 'equal' else
                                  l if point == j and i != j else l if end else k)
        return (max if end else min)(candidates) if candidates else 0

    offsets = [0]
    for line in source:
        offsets.append(offsets[-1] + len(line))
    regions = []
    for start, end in groups:
        original = ''.join(source[start:end])
        ranges = [(boundary(codes, start), boundary(codes, end, True)) for codes in opcodes]
        values = [''.join(side[a:b]) for side, (a, b) in zip(sides, ranges)]
        conflict = values[0] != original and values[1] != original and values[0] != values[1]
        regions.append(MergeRegion(offsets[start], offsets[end], original, *values, *ranges, conflict))
    return MergeModel(base, left, right, tuple(regions))


class MergeSession:
    """Text plus live hunk ranges; manual edits and resolution decisions share undo."""
    def __init__(self, model):
        self.model = model
        self.text = model.base
        self.ranges = [(r.start, r.end) for r in model.regions]
        self.resolved = [False] * len(model.regions)
        self.history = []
        self.future = []

    def snapshot(self):
        return self.text, tuple(self.ranges), tuple(self.resolved)

    def restore(self, state):
        self.text, ranges, resolved = state
        self.ranges, self.resolved = list(ranges), list(resolved)

    def remember(self):
        self.history.append(self.snapshot())
        # Bound full-text history as well as document size.
        while len(self.history) > 100 or sum(len(s[0]) for s in self.history) > 16 * MAX_CHARS:
            self.history.pop(0)
        self.future.clear()

    def _replace(self, start, end, replacement, owner=None):
        value = self.text[:start] + replacement + self.text[end:]
        bounded(value)
        delta = len(replacement) - (end - start)
        updated = []
        old_fragment = self.text[start:end]
        mapping = SequenceMatcher(None, old_fragment, replacement, autojunk=True).get_opcodes() if owner is None and len(old_fragment) <= 8192 and len(replacement) <= 8192 else None
        def map_inside(point):
            if point <= start:
                return point
            if point >= end:
                return point + delta
            local = point-start
            if mapping:
                for tag, i, j, k, l in mapping:
                    if i <= local <= j:
                        return start+k+(local-i if tag == 'equal' else round((local-i)*(l-k)/max(1,j-i)))
            return start + round((point-start)*len(replacement)/max(1,end-start))
        for index, (a, b) in enumerate(self.ranges):
            if index == owner:
                updated.append((start, start + len(replacement)))
            elif b <= start and (a != b or a < start or owner is not None and index < owner):
                updated.append((a, b))
            elif a >= end:
                updated.append((a + delta, b + delta))
            else:
                updated.append((map_inside(a), map_inside(b)))
                self.resolved[index] = False
        self.ranges, self.text = updated, value

    def choose(self, index, side):
        if side not in ('left', 'right', 'base', 'both'):
            raise ValueError('Unknown resolution')
        region = self.model.regions[index]
        replacement = region.left + region.right if side == 'both' else getattr(region, side)
        bounded(self.text[:self.ranges[index][0]] + replacement + self.text[self.ranges[index][1]:])
        self.remember()
        self._replace(*self.ranges[index], replacement, owner=index)
        self.resolved[index] = True

    def edit(self, text):
        if text == self.text:
            return
        bounded(text)
        start = 0
        while start < min(len(text), len(self.text)) and text[start] == self.text[start]:
            start += 1
        tail = 0
        while tail < min(len(text), len(self.text)) - start and text[-tail-1] == self.text[-tail-1]:
            tail += 1
        end = len(self.text) - tail
        self.remember()
        self._replace(start, end, text[start:len(text)-tail if tail else len(text)])

    def mark_manual(self, index):
        self.remember()
        self.resolved[index] = True

    def apply_nonconflicting(self):
        candidates = [i for i, r in enumerate(self.model.regions) if not r.conflict and not self.resolved[i]]
        if not candidates:
            return
        preview = MergeSession(self.model)
        preview.restore(self.snapshot())
        for index in reversed(candidates):
            region = self.model.regions[index]
            value = region.right if region.left == region.base else region.left
            preview._replace(*preview.ranges[index], value, owner=index)
            preview.resolved[index] = True
        self.remember()
        self.restore(preview.snapshot())

    def undo(self):
        if self.history:
            self.future.append(self.snapshot())
            self.restore(self.history.pop())

    def redo(self):
        if self.future:
            self.history.append(self.snapshot())
            self.restore(self.future.pop())

    @property
    def unresolved(self):
        return sum(not value for value in self.resolved)
