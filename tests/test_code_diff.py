import unittest
from commonUtils.ui.code_editor.diff import compare_text, apply_change


class DiffTests(unittest.TestCase):
    def test_insert_delete_replace_unicode_and_final_newline(self):
        for left, right in [("a\nb\n", "a\n"), ("a\n", "a\nb\n"),
                            ("😀 left\n", "😀 right\n"), ("a\n", "a")]:
            model = compare_text(left, right)
            self.assertEqual(len(model.changes), 1)
            start, end, replacement = apply_change(model, 0, right)
            self.assertEqual(right[:start] + replacement + right[end:], left)
        self.assertIn("No newline", compare_text("a\n", "a").unified)

    def test_identical_stale_and_limits(self):
        self.assertEqual(compare_text("a", "a").changes, ())
        with self.assertRaises(ValueError):
            apply_change(compare_text("a", "b"), 0, "changed")
        with self.assertRaises(ValueError):
            compare_text("a\n" * 5001, "")
