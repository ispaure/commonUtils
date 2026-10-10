import unittest
from commonUtils.ui.code_editor.formatting import format_text, validate_text


class FormattingTests(unittest.TestCase):
    def test_json_preserves_tokens_and_final_newline(self):
        source = '{"n":1.12345678901234567890,"n":1e+90,"s":"😀 \\"ok\\"","a":[]}\n'
        result = format_text(source, "json", 2)
        self.assertIn("1.12345678901234567890", result)
        self.assertIn("1e+90", result)
        self.assertEqual(result.count('"n"'), 2)
        self.assertTrue(result.endswith("\n"))
        validate_text(result, "json")
        self.assertEqual(format_text(result, "json", 2), result)

    def test_xml_comments_and_idempotence(self):
        source = '<root><!--keep--><item a="😀">text</item><empty/></root>'
        result = format_text(source, "xml", 2)
        self.assertIn("<!--keep-->", result)
        self.assertIn('a="😀"', result)
        self.assertEqual(format_text(result, "xml", 2), result)

    def test_refuses_unsafe_xml_invalid_json_and_oversize(self):
        for source, language in [('NaN', 'json'), ('{', 'json'),
                                 ('<!DOCTYPE x [<!ENTITY x "value">]><x/>', 'xml'),
                                 ('<a>before<b/>after</a>', 'xml'),
                                 ('<a xml:space="preserve">  <b/> </a>', 'xml'),
                                 (' ' * (1024 * 1024 + 1), 'json')]:
            with self.assertRaises(Exception):
                format_text(source, language)
        validate_text('<a>before<b/>after</a>', 'xml')
