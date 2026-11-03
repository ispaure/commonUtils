"""Size hints and native HTML are inert, bounded and source-independent."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
import os
from commonUtils.formats.markdown.images import image_size
from commonUtils.ui.native.markdown_preview import markdown_preview
from commonUtils.tests.formats.test_gif_headers import GIF


class MarkdownImageSyntaxTests(unittest.TestCase):
    def test_qt_image_resources_use_decoded_then_literal_paths(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from commonUtils.ui import pyside as qt
        from commonUtils.ui.markdown.images import local_image_path, local_image_resource
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / 'base%20folder'
            root.mkdir()
            literal, decoded = root / 'Two%20Words.gif', root / 'Two Words.gif'
            literal.write_bytes(GIF)
            base = qt.QUrl.fromLocalFile(str(root / 'Home.md'))
            target = qt.QUrl('Two%20Words.gif')
            self.assertEqual(local_image_path(target, base), literal)
            self.assertEqual(local_image_path(base.resolved(target), base), literal)
            self.assertFalse(local_image_resource(qt.QTextDocument.ResourceType.ImageResource, target, base).isNull())
            decoded.write_bytes(GIF)
            self.assertEqual(local_image_path(target, base), decoded)
            self.assertEqual(local_image_path(qt.QUrl('Two%2520Words.gif'), base), literal)

    def test_qt_denied_decoded_image_cannot_use_literal_or_default_loader(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from commonUtils.ui import pyside as qt
        from commonUtils.ui.markdown.images import local_image_resource
        from commonUtils.filesystem.local_access import protect_local_root
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            literal, decoded = root / 'Two%20Words.gif', root / 'Two Words.gif'
            literal.write_bytes(GIF)
            decoded.write_bytes(GIF)
            release = protect_local_root(object(), decoded, 'Private image')
            try:
                image = local_image_resource(qt.QTextDocument.ResourceType.ImageResource,
                                             qt.QUrl('Two%20Words.gif'),
                                             qt.QUrl.fromLocalFile(str(root / 'Home.md')))
                self.assertIsNotNone(image)
                self.assertTrue(image.isNull())
            finally:
                release()

    @unittest.skipUnless(os.name == 'nt', 'Windows drive paths')
    def test_qt_absolute_image_on_another_drive(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from commonUtils.ui import pyside as qt
        from commonUtils.ui.markdown.images import local_image_path
        with TemporaryDirectory() as temporary:
            image = Path(temporary) / 'Two%20Words.gif'
            image.write_bytes(GIF)
            drive = 'Y:' if image.drive.upper() == 'Z:' else 'Z:'
            base = qt.QUrl.fromLocalFile(drive + '/notes/Home.md')
            target = qt.QUrl.fromLocalFile(str(image.with_name('Two Words.gif')))
            self.assertEqual(local_image_path(target, base), image)

    def test_pasted_image_uses_destination_and_preserves_literal_contexts(self):
        from commonUtils.formats.markdown.images import image_targets
        source = r'![Concept_Katia_01_SD.jpg]\(Concept_Katia_01_SD.webp)'
        calls = []
        html = markdown_preview(source, image_source=lambda path: calls.append(path) or ('image/gif', GIF))
        self.assertEqual(calls, ['Concept_Katia_01_SD.webp'])
        self.assertIn('<img', html)
        self.assertIn('alt="Concept_Katia_01_SD.jpg"', html)
        self.assertEqual(image_targets(source), ('Concept_Katia_01_SD.webp',))
        for literal in ('`' + source + '`', '```\n' + source + '\n```', '\\' + source, '    ' + source):
            self.assertFalse(image_targets(literal))
            self.assertNotIn('<img', markdown_preview(literal, image_source=lambda path: ('image/gif', GIF)))

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
