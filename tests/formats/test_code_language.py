"""Toolkit-independent language identities and automatic/manual transitions."""
import unittest
from unittest.mock import patch

from commonUtils.formats.code_language import LANGUAGE_CHOICES, LanguageSelection, language_choices, language_label


class LanguageSelectionTests(unittest.TestCase):
    def test_automatic_and_manual_plain_text_are_distinct_across_renames(self):
        selection = LanguageSelection()
        selection.update('sample.py', 'print(1)')
        self.assertTrue(selection.automatic)
        self.assertEqual(selection.language_id, 'python')
        self.assertEqual(language_label(selection.language_id), 'Python')
        selection.select('text')
        selection.update('sample.json', '{}')
        self.assertFalse(selection.automatic)
        self.assertEqual(selection.language_id, 'text')
        self.assertEqual(selection.detected_id, 'json')
        selection.select(None)
        self.assertEqual(selection.language_id, 'json')

    def test_shebang_detection_manual_override_and_document_isolation(self):
        first, second = LanguageSelection(), LanguageSelection()
        first.update('', '#!/usr/bin/env python\nprint(1)')
        self.assertEqual(first.language_id, 'python')
        first.select('json')
        first.update('', '#!/bin/sh\necho hi')
        self.assertEqual(first.language_id, 'json')
        self.assertEqual(first.detected_id, 'bash')
        first.select(None)
        self.assertEqual(first.language_id, 'bash')
        self.assertEqual(second.language_id, 'text')
        self.assertTrue(second.automatic)

    def test_detection_reuses_unchanged_prefix_and_bounds_source_retention(self):
        selection = LanguageSelection()
        with patch('commonUtils.formats.code_language.detect_language', return_value='python') as detect:
            selection.update('sample.py', 'x' * 500)
            selection.update('sample.py', 'x' * 256 + 'changed suffix')
            detect.assert_called_once_with('sample.py', 'x' * 256)

    def test_desktop_extensions_keep_shared_ids_and_unique_labels(self):
        extended = language_choices(extended=True)
        self.assertEqual(extended[:2], LANGUAGE_CHOICES[:2])
        self.assertEqual(len({choice.id for choice in extended}), len(extended))
        self.assertEqual(len({choice.label for choice in extended}), len(extended))
        by_id = {choice.id: choice.label for choice in extended}
        for choice in language_choices():
            self.assertEqual(by_id[choice.id], choice.label)
        self.assertIn('ruby', by_id)

    def test_invalid_ids_are_rejected_without_changing_selection(self):
        selection = LanguageSelection()
        selection.select('python')
        for value in ('', '  ', 1, [], 'x' * 101):
            with self.subTest(value=value), self.assertRaises(ValueError):
                selection.select(value)
            self.assertEqual(selection.selected_id, 'python')
        # Historical/extended aliases remain representable even outside the
        # curated native list; the rendering adapter handles lexer availability.
        selection.select('ruby')
        self.assertEqual(selection.language_id, 'ruby')


if __name__ == '__main__':
    unittest.main()
