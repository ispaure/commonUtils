"""Portable wiki catalog contracts without importing Qt viewer fixtures."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commonUtils.formats.markdown.wiki import MarkdownWiki
from commonUtils.filesystem.directories import Directory


class WikiCatalogTests(unittest.TestCase):
    def test_landing_title_search_and_links(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            folder = root / 'test'
            folder.mkdir()
            (folder / 'test.md').write_text('# Apple\n\nSpecial fruit')
            (folder / 'child.md').write_text('# Child\n\nNeedle in source')
            (root / 'blank.md').write_text('\n# After blank')
            (root / 'metadata.md').write_text('---\nx: y\n---\n# After properties')
            (root / 'setext.md').write_text('Setext title\n====\n')
            (root / 'linked').symlink_to(folder, target_is_directory=True)
            catalog = MarkdownWiki(Directory(root))
            parent = next(e for e in catalog.entries if e.location == folder)
            self.assertEqual(parent.title, 'Apple')
            self.assertEqual(parent.page, folder / 'test.md')
            self.assertEqual(catalog.parent_page(folder / 'child.md'), folder / 'test.md')
            self.assertIsNone(catalog.parent_page(folder / 'test.md'))
            self.assertEqual([e.title for e in parent.children], ['Child'])
            self.assertEqual(catalog.search('apple')[0].page, folder / 'test.md')
            self.assertEqual(catalog.search('needle', 'content')[0].children[0].page, folder / 'child.md')
            self.assertEqual(catalog.search('missing'), ())
            names = {e.title for e in catalog.entries}
            self.assertTrue({'After blank', 'After properties', 'Setext title'} <= names)
            self.assertFalse(any(e.location.name == 'linked' for e in catalog.entries))

    def test_same_named_root_is_single_parent_and_search_keeps_ancestry(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / 'docs'
            root.mkdir()
            home, child = root / 'docs.md', root / 'child.md'
            home.write_text('# Documentation')
            child.write_text('# Child\nNeedle')
            catalog = MarkdownWiki(root)
            self.assertEqual(len(catalog.entries), 1)
            entry = catalog.entries[0]
            self.assertEqual((entry.location, entry.page), (root, home))
            self.assertEqual([e.page for e in entry.children], [child])
            self.assertEqual(catalog.search('needle', 'content')[0].children[0].page, child)
            self.assertEqual(catalog.parent_page(child), home)
            self.assertIsNone(catalog.parent_page(home))

    def test_heading_after_properties_and_blank_lines(self):
        for text in ('---\ntags: [fruit]\n---\n# Apple',
                     '---\n# YAML comment\ntags: [fruit]\n---\n\n\n# Apple ##',
                     '\ufeff---\ntitle: Other\n---\r\n\r\nApple\r\n====',
                     '\n   \n# Apple',
                     '---\ntags: [fruit]\n...\n\n# Apple'):
            with self.subTest(text=text):
                self.assertEqual(MarkdownWiki.title(text, 'fallback'), 'Apple')
        for text in ('---\ntags: [fruit]\n# YAML comment without closing delimiter',
                     '---\ntags: [fruit]\n---\nIntroduction\n\n# Later heading',
                     '---\ntags: [fruit]\n---\n\n',
                     '    # Indented code'):
            with self.subTest(text=text):
                self.assertEqual(MarkdownWiki.title(text, 'fallback'), 'fallback')
