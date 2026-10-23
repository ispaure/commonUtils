"""Provider-backed native GIFs preserve bytes, names and access boundaries."""
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.tests.formats.test_gif_headers import GIF
from commonUtils.ui.native.markdown_images import folder_image_source
from commonUtils.ui.native.markdown_preview import markdown_preview


class NativeMarkdownImageTests(unittest.TestCase):
    def setUp(self):
        self.scope = TemporaryDirectory()
        self.addCleanup(self.scope.cleanup)
        self.root = Path(self.scope.name)
        (self.root / 'notes').mkdir()
        self.image = self.root / 'colors #1 %.GIF'
        self.image.write_bytes(GIF)
        self.provider = LocalFiles(self.root)
        self.load = folder_image_source(self.provider, 'notes/page.md')
        self.target = '../colors%20%231%20%25.GIF'

    def test_exact_animated_bytes_encoded_filename_and_wiki_embed(self):
        self.assertEqual(self.load(self.target), ('image/gif', GIF))
        html = markdown_preview(f'![Colors]({self.target})\n\n![[{self.target}]]', image_source=self.load)
        self.assertEqual(html.count('<img src="data:image/gif;base64,'), 2)
        self.assertEqual(html.count(base64.b64encode(GIF).decode()), 2)
        self.assertIn('img-src data:', html)
        self.assertNotIn('file://', html)
        self.assertNotIn('<img', markdown_preview(f'![Colors]({self.target})'))
        for text in (f'`![Colors]({self.target})`', f'```\n![[{self.target}]]\n```', f'\\![[{self.target}]]'):
            self.assertNotIn('<img', markdown_preview(text, image_source=self.load))

    def test_root_url_query_and_link_guards(self):
        for target in ('../../escape.gif', '%2e%2e/%2e%2e/escape.gif', '/outside.gif',
                       '%2foutside.gif', 'https://host/a.gif', '//host/a.gif', 'file:///a.gif',
                       'data:image/gif;base64,abc', '../a.gif?x=1', '../a%00.gif', '../a%5cb.gif'):
            with self.subTest(target=target), patch.object(self.provider, 'open', side_effect=AssertionError('raw open')):
                self.assertIsNone(self.load(target))
        (self.root / 'linked.gif').symlink_to(self.image)
        self.assertNotIn('<img', markdown_preview('![Linked](../linked.gif)', image_source=self.load))

    def test_changed_or_revoked_cached_images_are_not_reused(self):
        self.load(self.target)
        with patch.object(self.provider, 'entry', side_effect=PermissionError('Locked')):
            self.assertNotIn('<img', markdown_preview(f'![Locked]({self.target})', image_source=self.load))
        self.image.write_bytes(GIF + b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.load(self.target)

    def test_mutation_during_read_and_invalid_gif_fall_back_to_alt(self):
        before = self.provider.entry(self.image.name)
        with patch.object(self.provider, 'entry', side_effect=[before, dict(before, revision='changed')]):
            with self.assertRaisesRegex(ValueError, 'changed'):
                self.load(self.target)
        for data in (GIF[:-1], b'GIF89a', b'not an image'):
            self.image.write_bytes(data)
            html = markdown_preview(f'![Bad & image]({self.target})',
                image_source=folder_image_source(self.provider, 'notes/page.md'))
            self.assertNotIn('<img', html)
            self.assertIn('Bad &amp; image', html)

    def test_canvas_and_byte_budget_checks_precede_embedding(self):
        self.image.write_bytes(GIF[:6] + b'\xff\xff\xff\xff' + GIF[10:])
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            self.load(self.target)
        self.image.write_bytes(b'X' * (8 * 1024 * 1024 + 65))
        with patch.object(self.provider, 'open', side_effect=AssertionError('oversized open')):
            self.assertIsNone(self.load(self.target))
