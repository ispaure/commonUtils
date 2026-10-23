"""Three-way resolution invariants, live ranges, Unicode and reversible edits."""
import random
import unittest
from commonUtils.persistence.merge import MergeSession, merge_text


class MergeModelTests(unittest.TestCase):
    def test_nonoverlapping_edits_and_equal_edits(self):
        session = MergeSession(merge_text('a\nb\nc\n', 'left\nb\nc\n', 'a\nb\nright\n'))
        session.apply_nonconflicting()
        self.assertEqual(session.text, 'left\nb\nright\n')
        self.assertEqual(session.unresolved, 0)
        session.undo(); self.assertEqual(session.text, 'a\nb\nc\n')
        session.redo(); self.assertEqual(session.unresolved, 0)

    def test_overlapping_changes_both_manual_and_history(self):
        session = MergeSession(merge_text('a\nb\nc\n', 'a\n😀 left\nc\n', 'a\nright\nc\n'))
        self.assertTrue(session.model.regions[0].conflict)
        session.apply_nonconflicting(); self.assertEqual(session.unresolved, 1)
        session.choose(0, 'both'); self.assertEqual(session.text, 'a\n😀 left\nright\nc\n')
        session.undo(); self.assertEqual(session.unresolved, 1)
        session.edit('a\nmanual\nc\n'); self.assertEqual(session.unresolved, 1)
        session.mark_manual(0); self.assertEqual(session.unresolved, 0)
        session.undo(); self.assertEqual(session.unresolved, 1)
        session.undo(); self.assertEqual(session.text, 'a\nb\nc\n')
        session.redo(); self.assertEqual(session.text, 'a\nmanual\nc\n')

    def test_range_tracking_after_earlier_accept_and_manual_edit(self):
        session = MergeSession(merge_text('a\nb\nc\n', 'long left\nb\nleft c\n', 'a\nb\nright c\n'))
        session.choose(0, 'left')
        session.edit('prefix\n'+session.text)
        session.choose(1, 'right')
        self.assertEqual(session.text, 'prefix\nlong left\nb\nright c\n')
        session.undo(); self.assertEqual(session.text, 'prefix\nlong left\nb\nc\n')

    def test_insertions_deletions_and_final_newline(self):
        for base,left,right,expected in [('', 'left\n', 'right\n', 'left\n'),
            ('a\nb\n', 'a\n', 'a\nchanged\n', 'a\n'),
            ('a\n', 'a', 'changed\n', 'a')]:
            session=MergeSession(merge_text(base,left,right))
            self.assertEqual(session.unresolved, 1)
            session.choose(0, 'left'); self.assertEqual(session.text, expected)

    def test_randomized_one_sided_and_identical_side_invariants(self):
        randomizer = random.Random(42)
        for _ in range(200):
            base=''.join(randomizer.choice('ab😀')+'\n' for _ in range(randomizer.randrange(10)))
            changed=''.join(randomizer.choice('ab😀')+'\n' for _ in range(randomizer.randrange(10)))
            for left,right in [(base, changed), (changed, base), (changed, changed)]:
                session=MergeSession(merge_text(base,left,right)); session.apply_nonconflicting()
                self.assertEqual(session.text, changed); self.assertEqual(session.unresolved, 0)

    def test_bounds_and_invalid_resolution_preserve_state(self):
        with self.assertRaises(ValueError): merge_text('a\n'*5001, '', '')
        session=MergeSession(merge_text('a', 'left', 'right'))
        before=session.snapshot()
        with self.assertRaises(ValueError): session.choose(0, 'unknown')
        with self.assertRaises(ValueError): session.edit('x'* (1024*1024+1))
        self.assertEqual(session.snapshot(), before)

    def test_randomized_resolution_and_manual_history_roundtrips_exact_snapshots(self):
        randomizer = random.Random(20261010)
        for scenario in range(100):
            session = MergeSession(merge_text('a\nb\nc\n', '😀 left\nb\nleft c', 'right\nb\n😀 right c\n'))
            states = [session.snapshot()]
            for step in range(30):
                choice = randomizer.randrange(3)
                if choice == 0:
                    session.choose(randomizer.randrange(len(session.model.regions)), randomizer.choice(('left', 'right', 'both', 'base')))
                elif choice == 1:
                    position = randomizer.randrange(len(session.text)+1)
                    session.edit(session.text[:position] + randomizer.choice(('😀', '\n', 'paste\nmore')) + session.text[position:])
                else:
                    session.mark_manual(randomizer.randrange(len(session.model.regions)))
                states.append(session.snapshot())
            for expected in reversed(states[:-1]):
                session.undo(); self.assertEqual(session.snapshot(), expected, (scenario, 'undo'))
            for expected in states[1:]:
                session.redo(); self.assertEqual(session.snapshot(), expected, (scenario, 'redo'))
            session.undo(); session.edit(session.text + 'branch')
            self.assertFalse(session.future)
            before = session.snapshot(); session.redo(); self.assertEqual(session.snapshot(), before)
