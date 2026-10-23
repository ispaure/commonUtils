"""Size hints and native HTML are inert, bounded and source-independent."""
import unittest
from commonUtils.formats.markdown.images import image_size
from commonUtils.ui.native.markdown_preview import markdown_preview
from commonUtils.tests.formats.test_gif_headers import GIF


class MarkdownImageSyntaxTests(unittest.TestCase):
    def test_width_height_and_caption(self):
        for text, expected in [('Caption|400', ('Caption', 400, None)), ('400', ('', 400, None)),
                               ('Caption|400x200', ('Caption', 400, 200)), ('400x200', ('', 400, 200)),
                               ('Caption|part|70', ('Caption|part', 70, None))]:
            self.assertEqual(image_size(text), expected)
        for text in ('Caption', '', '0', '-20', '1.5', '200%', '100x0', '1000000',
                     'x400', '400x', 'caption|100 onload=bad', '9' * 5000):
            self.assertEqual(image_size(text), (text, None, None))

    def test_native_width_cap_size_hints_and_escaped_caption(self):
        load = lambda target: ('image/gif', GIF)
        for source in ('![Caption|400](image.gif)', '![[image.gif|400]]', '![400](image.gif)'):
            with self.subTest(source=source):
                html = markdown_preview(source, image_source=load)
                self.assertIn('width="400"', html)
                self.assertIn('max-width:100%;height:auto;width:400px', html)
        html = markdown_preview('![A & B|400x200](image.gif)', image_source=load)
        self.assertIn('alt="A &amp; B" width="400" height="200"', html)
        self.assertIn('aspect-ratio:400/200', html)
        for source in ('`![[image.gif|400]]`', '```\n![Caption|400](image.gif)\n```'):
            self.assertNotIn('<img', markdown_preview(source, image_source=load))

    def test_wiki_paths_encode_spaces_and_hash_before_provider_resolution(self):
        calls = []
        html = markdown_preview('![[colors #1.GIF|70]]',
            image_source=lambda path: calls.append(path) or ('image/gif', GIF))
        self.assertEqual(calls, ['colors%20%231.GIF'])
        self.assertIn('width="70"', html)
        self.assertNotIn('alt="colors #1.GIF|70"', html)
