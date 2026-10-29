"""Native wiki is reusable without Logistics or Qt installed."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest

from commonUtils.ui.native.markdown_preview import markdown_preview


class NativeMarkdownTests(unittest.TestCase):
    def test_host_supplied_images_are_opt_in_and_cannot_inject_markup(self):
        calls = []
        def image(target):
            calls.append(target)
            return 'image/webp', b'fixture'
        html = markdown_preview('![A & B](photo.webp) ![[other.webp]]', image_source=image)
        self.assertEqual(calls, ['photo.webp', 'other.webp'])
        self.assertEqual(html.count('<img src="data:image/webp;base64,'), 2)
        self.assertIn('alt="A &amp; B"', html)
        self.assertIn('img-src data:', html)
        self.assertNotIn('<img', markdown_preview('![A](photo.webp)'))
        self.assertNotIn('<img', markdown_preview('![A](photo.webp)',
            image_source=lambda target: ('image/svg+xml', b'<svg/>')))
        self.assertNotIn('<img', markdown_preview('![A](photo.webp)',
            image_source=lambda target: (_ for _ in ()).throw(OSError('Missing'))))

    def test_common_markdown_and_tables(self):
        html = markdown_preview('''# Main *title*
## Repeated
## Repeated

Setext title
------------

| Feature | Status | Count |
| :--- | :---: | ---: |
| **Tables** | *Ready* | 2 |
| Escaped \\| pipe | `code` | 3 |

1. First
   - Nested
     - Deeper
2. Second

> A **quote**
>
> Another paragraph

Normal wrapped
paragraph with _emphasis_, ~~old~~ and **bold**.\x20\x20
Hard break.

---

~~~python
<literal> **source**
~~~
''')
        self.assertIn('<h1 id="main-title">Main <em>title</em></h1>', html)
        self.assertIn('id="repeated-1"', html)
        self.assertIn('<h2 id="setext-title">', html)
        self.assertIn('<table>', html)
        self.assertEqual(html.count('<td'), 6)
        self.assertIn('style="text-align:center"', html)
        self.assertIn('style="text-align:right"', html)
        self.assertIn('Escaped | pipe', html)
        self.assertIn('<ol>', html)
        self.assertEqual(html.count('<ul>'), 2)
        self.assertIn('<blockquote>', html)
        self.assertIn('<em>emphasis</em>', html)
        self.assertIn('<s>old</s>', html)
        self.assertIn('Normal wrapped\nparagraph', html)
        self.assertIn('<br />', html)
        self.assertIn('<hr />', html)
        self.assertIn('&lt;literal&gt; **source**', html)

    def test_reference_anchor_escaped_code_and_inert_images(self):
        html = markdown_preview('''[Next][page] [Section](#a-heading)

[page]: folder/next.md "Next page"

`[Next](bad.md)` \\*literal\\*

![Remote **image**](https://example.invalid/image.png)
<script>alert(1)</script>
[Script](javascript:alert%281%29) [Web](https://example.org)
''', local_links=True)
        self.assertIn('href="folder/next.md"', html)
        self.assertIn('href="#a-heading"', html)
        self.assertIn('<code>[Next](bad.md)</code>', html)
        self.assertIn('*literal*', html)
        self.assertIn('Remote image', html)
        self.assertNotIn('<img', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('href="javascript:', html)
        self.assertNotIn('href="https:', html)

    def test_inert_links_and_bounds(self):
        html = markdown_preview('[Page](folder/page.md) [External](https://example.org/a.md)', local_links=True)
        self.assertIn('href="folder/page.md"', html)
        self.assertNotIn('href="https:', html)
        self.assertNotIn('<a href=', markdown_preview('[Page](folder/page.md)'))
        self.assertIn('&lt;script&gt;', markdown_preview('<script>alert(1)</script>'))
        with self.assertRaises(ValueError):
            markdown_preview('x' * (1024 * 1024 + 1))

    def test_alias_and_standard_links_share_destination(self):
        html = markdown_preview('[test.md|Test] [Test](test.md) [[test.md|Test]]', local_links=True)
        self.assertEqual(html.count('<a href="test.md">Test</a>'), 3)
        self.assertIn('href="../some%20page.md"', markdown_preview('[../some page.md|Other]', local_links=True))
        literal = markdown_preview('`[test.md|Test]` ` [Test](test.md)`', local_links=True)
        self.assertNotIn('<a href=', literal)

    def test_bare_wiki_links_in_headings_preserve_code_and_embeds(self):
        html = markdown_preview('# **[[Tech]]**\n\n`[[Literal]]`\n\n![[photo.png]] ![[other.png|Caption]]', local_links=True)
        self.assertIn('<a href="Tech">Tech</a>', html)
        self.assertNotIn('href="Literal"', html)
        self.assertNotIn('href="photo.png"', html)
        self.assertNotIn('href="other.png"', html)

    @unittest.skipUnless(importlib.util.find_spec('toga'), 'Optional Toga backend is not installed')
    def test_standalone_phone_tablet_search_without_consumer_or_qt(self):
        script = '''
import importlib.abc, sys
from pathlib import Path
from tempfile import TemporaryDirectory
class Reject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'logisticsmobile', 'features', 'PySide6'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Reject())
import toga
from commonUtils.ui.native.markdown import MarkdownWikiView
app = toga.App('Standalone wiki', 'org.example.markdown-wiki')
with TemporaryDirectory() as temporary:
    root = Path(temporary).resolve()
    (root / 'README.md').write_text('# Home')
    folder = root / 'test'
    folder.mkdir()
    (folder / 'test.md').write_text('# Apple')
    child = folder / 'child.md'
    child.write_text('# Child\\n\\nNeedle')
    (root / 'other.md').write_text('# Other')
    (root / 'example.py').write_text('print("hello")')
    wiki = MarkdownWikiView(directory=root, width=390)
    assert wiki.path == root / 'README.md'
    assert [b.control_icon for b in (wiki.back_button, wiki.forward_button, wiki.up_button)] == ['back', 'forward', 'up']
    assert [b.accessible_name for b in (wiki.back_button, wiki.forward_button, wiki.up_button)] == ['Back', 'Forward', 'Up to parent folder page']
    assert all(b.style.width == 48 and b.style.height == 48 for b in (wiki.back_button, wiki.forward_button, wiki.up_button))
    assert list(wiki.content.children) == [wiki.article]
    assert wiki.browse_button in wiki.navigation.children
    wiki.browse_button.on_press()
    assert list(wiki.content.children) == [wiki.browse]
    wiki.browse_button.on_press()
    assert list(wiki.content.children) == [wiki.article]
    wiki.show_browse()
    assert list(wiki.content.children) == [wiki.browse]
    wiki.search.value = 'needle'
    wiki.mode.value = 'Page text'
    wiki.filter()
    assert len(wiki.rows.children) == 2
    wiki.rows.children[-1].children[-1].on_press()
    assert wiki.path == child
    original = (wiki.search, wiki.web, wiki.rows)
    history = list(wiki.history)
    wiki.reflow(900)
    assert list(wiki.content.children) == [wiki.browse, wiki.article]
    assert wiki.browse_button not in wiki.navigation.children
    assert wiki.search.value == 'needle'
    assert wiki.path == child
    wiki.reflow(390)
    assert list(wiki.content.children) == [wiki.article]
    assert wiki.browse_button in wiki.navigation.children
    assert wiki.history == history
    assert original == (wiki.search, wiki.web, wiki.rows)
    for width in (1024, 520, 800, 390):
        wiki.reflow(width)
        assert wiki.wide == (width >= 744)
        assert wiki.path == child
        assert wiki.search.value == 'needle'
    stale_url = wiki.base
    wiki.follow_link(wiki.web, 'test.md')
    assert wiki.title.text == 'Apple'
    position = wiki.history_index
    assert wiki.follow_link(wiki.web, stale_url) is False
    assert wiki.history_index == position
    assert wiki.path == folder / 'test.md'
    assert wiki.follow_link(wiki.web, wiki.base) is False
    assert wiki.history_index == position
    assert wiki.up_button.enabled
    wiki.up_button.on_press()
    assert wiki.path == root / 'README.md'
    assert not wiki.up_button.enabled
    wiki.back_button.on_press()
    assert wiki.path == folder / 'test.md'
    assert wiki.forward_button.enabled
    wiki.forward_button.on_press()
    assert wiki.path == root / 'README.md'
    wiki.back()
    wiki.open_page(child)
    assert not wiki.forward_button.enabled
    wiki.up()
    assert wiki.path == folder / 'test.md'
    wiki.back()
    assert wiki.path == child
    wiki.forward()
    assert wiki.path == folder / 'test.md'
    from urllib.parse import quote
    opened = []
    wiki.open_file = opened.append
    history = list(wiki.history)
    wiki.follow_link(wiki.web, wiki.base + '?target=' + quote('../example.py', safe=''))
    assert opened == [root / 'example.py']
    assert wiki.history == history
    assert wiki.path == folder / 'test.md'
    wiki.follow_link(wiki.web, wiki.base + '?target=' + quote('../other', safe=''))
    assert wiki.path == root / 'other.md'
    wiki.back()
    assert wiki.path == folder / 'test.md'
    (root / 'unlisted.md').write_text('# Unlisted')
    wiki.follow_link(wiki.web, '../unlisted')
    assert wiki.path == root / 'unlisted.md'
    wiki.back()
    assert wiki.path == folder / 'test.md'
    wiki.forward()
    assert wiki.path == root / 'unlisted.md'
    wiki.back()
    wiki.follow_link(wiki.web, '../../outside.md')
    assert wiki.path == folder / 'test.md'
    wiki.back()
    index = wiki.history_index
    (folder / 'test.md').unlink()
    assert wiki.forward() is False
    assert wiki.history_index == index
    assert wiki.path == child
'''
        environment = dict(os.environ, TOGA_BACKEND='toga_dummy')
        result = subprocess.run([sys.executable, '-c', script], env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
