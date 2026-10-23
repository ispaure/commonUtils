"""The shared documentation opens as one titled, linked Markdown wiki."""
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

from commonUtils.formats.markdown import split_frontmatter
from commonUtils.formats.markdown.wiki import MarkdownWiki, documentation_root

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'


def local_links(page):
    text = re.sub(r'^```.*?^```[^\n]*', '', page.read_text(), flags=re.M | re.S)
    text = re.sub(r'`[^`\n]*`', '', text)
    for url in re.findall(r'\[[^\]\n]*\]\(([^\s)]+)', text):
        parsed = urlsplit(url)
        if not parsed.scheme and not parsed.netloc and parsed.path:
            yield (page.parent / unquote(parsed.path)).resolve()


class DocumentationLayoutTests(unittest.TestCase):
    def test_all_pages_share_the_root_wiki_and_have_h1_titles(self):
        wiki = MarkdownWiki(DOCS)
        self.assertFalse(wiki.errors)
        self.assertTrue(wiki.pages)
        for page, text in wiki.pages.items():
            with self.subTest(page=page.relative_to(ROOT)):
                self.assertTrue(split_frontmatter(text).body.lstrip().startswith('# '))
                self.assertEqual(documentation_root(page), DOCS)
                for target in local_links(page):
                    self.assertTrue(target.exists(), str(target))

    def test_each_folder_landing_links_every_immediate_child(self):
        for folder in [DOCS, *[p for p in DOCS.rglob('*') if p.is_dir()]]:
            landing = folder / (folder.name + '.md')
            with self.subTest(folder=folder.relative_to(ROOT)):
                self.assertTrue(landing.is_file())
                linked = set(local_links(landing))
                for child in folder.iterdir():
                    target = child / (child.name + '.md') if child.is_dir() else child
                    if target != landing and target.suffix == '.md':
                        self.assertIn(target.resolve(), linked)

    def test_legacy_component_and_perforce_paths_are_short_links(self):
        for relative in ('ui/markdown/user_docs/README.md', 'filesystem/index/README.md',
                         'integrations/wrappers/perforce/developer-guide.md'):
            page = ROOT / relative
            self.assertLessEqual(len(page.read_text().splitlines()), 5)
            self.assertTrue(any(p.is_relative_to(DOCS) for p in local_links(page)))
