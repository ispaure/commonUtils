"""Provider-backed native GIFs preserve bytes, names and access boundaries."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.tests.formats.test_gif_headers import GIF
from commonUtils.formats.markdown.image_sources import folder_image_source
from commonUtils.ui.native.markdown_preview import markdown_preview


class NativeMarkdownImageTests(unittest.TestCase):
    def test_caller_image_budget_is_per_render_and_keeps_the_default(self):
        load = folder_image_source(self.provider, 'notes/page.md', max_total_bytes=2 * len(GIF))
        (self.root / 'notes/budget.gif').write_bytes(GIF)
        self.assertEqual(load('budget.gif'), ('image/gif', GIF))
        self.assertEqual(load('budget.gif'), ('image/gif', GIF))
        with self.assertRaisesRegex(ValueError, 'preview budget'):
            load('budget.gif')
        fresh = folder_image_source(self.provider, 'notes/page.md', max_total_bytes=2 * len(GIF))
        self.assertEqual(fresh('budget.gif'), ('image/gif', GIF))
        with self.assertRaises(ValueError):
            folder_image_source(self.provider, 'notes/page.md', max_total_bytes=0)

    def test_failures_explain_missing_access_invalid_and_oversized_images(self):
        cases = ((FileNotFoundError('/private/path'), 'File not found'),
                 (PermissionError('/private/path'), 'Access denied'),
                 (ValueError('Several attachments match <photo> & name.'),
                  'Several attachments match &lt;photo&gt; &amp; name.'))
        for error, reason in cases:
            with self.subTest(error=error):
                def fail(target):
                    raise error
                html = markdown_preview('![Photo](photo.gif)', image_source=fail)
                self.assertIn('Image unavailable: ' + reason, html)
                self.assertNotIn('/private/path', html)
                self.assertNotIn('<img', html)
        self.image.write_bytes(b'X' * (8 * 1024 * 1024 + 65))
        html = markdown_preview(f'![Photo]({self.target})', image_source=self.load)
        self.assertIn('8 MiB', html)

    def test_host_resolver_result_is_still_scoped_and_access_checked(self):
        load = folder_image_source(self.provider, 'notes/page.md', root='notes',
                                   resolve=lambda target: self.image.name)
        with patch.object(self.provider, 'open', side_effect=AssertionError('outside read')):
            self.assertIsNone(load('photo.gif'))

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

    def test_percent_encoded_image_fallback_and_decoded_priority(self):
        (self.root / 'notes/Two%20Words').mkdir()
        raw = self.root / 'notes/Two%20Words/photo.gif'
        raw.write_bytes(GIF + b'literal')
        target = 'Two%20Words/photo.gif'
        self.assertEqual(self.load(target), ('image/gif', GIF + b'literal'))
        (self.root / 'notes/Two Words').mkdir()
        decoded = self.root / 'notes/Two Words/photo.gif'
        decoded.write_bytes(GIF + b'decoded')
        self.assertEqual(self.load(target), ('image/gif', GIF + b'decoded'))
        self.assertEqual(self.load('Two%2520Words/photo.gif'), ('image/gif', GIF + b'literal'))
        html = markdown_preview(r'![Photo]\(Two%20Words/photo.gif)', image_source=self.load)
        self.assertIn(base64.b64encode(GIF + b'decoded').decode(), html)

    def test_decoded_attachment_image_precedes_literal_relative_image(self):
        (self.root / 'notes/Attachments').mkdir()
        (self.root / 'notes/Attachments/Two Words.gif').write_bytes(GIF + b'decoded')
        (self.root / 'notes/Two%20Words.gif').write_bytes(GIF + b'literal')
        load = folder_image_source(self.provider, 'notes/page.md', root='notes')
        self.assertEqual(load('Two%20Words.gif'), ('image/gif', GIF + b'decoded'))

    def test_rejected_decoded_image_does_not_fall_back_to_literal_name(self):
        (self.root / 'notes/Two%20Words.gif').write_bytes(GIF + b'literal')
        (self.root / 'notes/Two Words.gif').symlink_to(self.image)
        with patch.object(self.provider, 'open', side_effect=AssertionError('read rejected image')):
            self.assertIsNone(self.load('Two%20Words.gif'))

    def test_encoded_extension_keeps_literal_filename_fallback(self):
        (self.root / 'notes/photo%2Egif').write_bytes(GIF + b'literal')
        self.assertEqual(self.load('photo%2Egif'), ('image/gif', GIF + b'literal'))
        (self.root / 'notes/photo.gif').write_bytes(GIF + b'decoded')
        self.assertEqual(self.load('photo%2Egif'), ('image/gif', GIF + b'decoded'))

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
            with self.assertRaisesRegex(ValueError, '8 MiB'):
                self.load(self.target)

    def test_library_root_and_attachment_fallbacks_stay_inside_the_library(self):
        (self.root / 'Vault/Notes').mkdir(parents=True)
        (self.root / 'Vault/Attachments').mkdir()
        (self.root / 'Vault/Attachments/photo.GIF').write_bytes(GIF)
        load = folder_image_source(self.provider, 'Vault/Notes/read.md', root='Vault')
        self.assertEqual(load('photo.GIF'), ('image/gif', GIF))
        self.assertEqual(load('Attachments/photo.GIF'), ('image/gif', GIF))
        for source in ('![Caption.jpg](photo.GIF)', r'![Caption.jpg]\(photo.GIF)', '![[photo.GIF]]'):
            self.assertIn('<img', markdown_preview(source, image_source=load))
        (self.root / 'Vault/Notes/photo.GIF').write_bytes(GIF + b'local')
        self.assertEqual(load('photo.GIF'), ('image/gif', GIF + b'local'))
        (self.root / 'Vault/.obsidian').mkdir()
        (self.root / 'Vault/.obsidian/secret.gif').write_bytes(GIF)
        for target in ('../../colors%20%231%20%25.GIF', '../.obsidian/secret.gif'):
            self.assertIsNone(load(target))
        with patch.object(self.provider, 'list', side_effect=AssertionError('recursive scan')):
            self.assertIsNone(load('absent.gif'))

    def test_image_destination_collection_handles_wiki_references_and_literal_hashes(self):
        from commonUtils.formats.markdown.images import image_targets
        text = ('![[two colors #1.PNG|900x600]]\n\n'
                '![Reference][photo]\n\n[photo]: <images/with space.webp> "Title"\n\n'
                r'![Concept_Katia_01_SD.jpg]\(Concept_Katia_01_SD.webp)' + '\n\n'
                '`![[code.png]]`\n\n```\n![[fenced.png]]\n```\n')
        self.assertEqual(image_targets(text), ('two%20colors%20%231.PNG', 'images/with%20space.webp', 'Concept_Katia_01_SD.webp'))
