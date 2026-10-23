"""Native and desktop syntax data share language definitions without Qt imports."""
import unittest
from unittest.mock import patch
from commonUtils.formats.code_spans import line_offsets, syntax_spans, MAX_HIGHLIGHT_CHARS
from commonUtils.formats.code_syntax import detect_language, LANGUAGES


class CodeSpanTests(unittest.TestCase):
    def test_typing_in_ordinary_notes_does_not_scan_the_lexer_registry(self):
        with patch('pygments.lexers.get_lexer_for_filename', side_effect=AssertionError('Scanned lexer registry')):
            self.assertEqual(detect_language('Note.MD', '# title'), 'markdown')
            self.assertEqual(detect_language('Note.markdown', 'changed text'), 'markdown')
            self.assertEqual(detect_language('Note.txt', 'plain text'), 'text')
            self.assertEqual(detect_language('settings.json', '{}'), 'json')

    def test_logical_line_starts_use_native_utf16_coordinates(self):
        self.assertEqual(line_offsets(''), [0])
        self.assertEqual(line_offsets('😀 one\nwrapped\n'), [0, 7, 15])
        self.assertEqual(line_offsets('a\r\nb'), [0, 3])

    def test_colours_preserve_multiline_grammar_and_unicode_offsets(self):
        text = 'value = """😀 first\nsecond"""\ndef hello():\n    return 42\n'
        language, spans = syntax_spans(text, 'sample.py')
        self.assertEqual(language, 'python')
        self.assertTrue(spans)
        size = len(text.encode('utf-16-le')) // 2
        self.assertTrue(all(0 <= start < end <= size and 0 <= rgb <= 0xffffff for start, end, rgb in spans))
        # Spans address the original string, including text after a surrogate pair.
        decoded = text.encode('utf-16-le')
        values = [decoded[start*2:end*2].decode('utf-16-le') for start, end, colour in spans]
        self.assertIn('return', values)
        self.assertIn('def', values)
        self.assertNotEqual(spans, syntax_spans(text, 'sample.py', dark=True)[1])

    def test_shared_languages_plain_override_and_large_document_fallback(self):
        for label, alias in LANGUAGES:
            with self.subTest(language=label):
                self.assertEqual(syntax_spans('value = "hello"\n', language=alias)[0], alias)
        self.assertEqual(detect_language('template.blade.php'), 'blade')
        self.assertEqual(syntax_spans('def x(): pass', 'x.py', language='text'), ('text', []))
        self.assertEqual(syntax_spans('x' * (MAX_HIGHLIGHT_CHARS + 1), 'x.py'), ('python', []))
