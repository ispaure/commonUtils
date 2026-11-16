"""Exercise portable speech preparation with rendered and source coordinates."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import unittest

from commonUtils.formats.markdown.speech import RenderedRun, prepare_markdown, prepare_rendered
from commonUtils.runtime.speech import utterances
from commonUtils.runtime.speech_text import utf16_length


MIXED = r"""---
private: Frontmatter secret
---
# 😀 Heading

[image.jpg](snoopy-died), [[Tech]], [[Tech|Technology]], and **emphasis**.
[Reference][ref] beside ![Image secret](image-target.jpg).
Visible caption.

[ref]: hidden-reference "Hidden title"

> [!note]- Closed
> Collapsed secret

> [!tip]+ **Open**
> Quote body

| Header | Next |
| :--- | ---: |
| One | [Two](secret-link) |

- [x] Complete
  - [ ] Pending

Footnotes[^1] and repeated[^1].

[^1]: One footnote only.
    Continuation of the footnote.

```python
f("<tag>") # code comment
<!-- visible in code -->
%%also code%%
```

<!-- Hidden HTML -->

Before %% hidden Obsidian %% and `<!-- literal -->`.
Escaped \* and \[literal\] and \$4.
This math $\frac{x}{2}$ is silent.

```dataview
LIST hidden query
```

```dataviewjs
await dv.io.load('private');
```

![[Cycle#Section|Unresolved note]]
"""


def portion(text, start, end):
    return text.encode('utf-16-le')[start * 2:end * 2].decode('utf-16-le')


def phrase_range(prepared, phrase):
    index = prepared.text.index(phrase)
    start = utf16_length(prepared.text[:index])
    return start, start + utf16_length(phrase)


class MarkdownSpeechTests(unittest.TestCase):
    def test_mixed_document_order_and_payload(self):
        prepared = prepare_markdown(MIXED)
        output = prepared.text
        ordered = ('😀 Heading', 'image.jpg', 'Tech', 'Technology', 'emphasis',
                   'Reference', 'Visible caption.', 'Closed', 'Open', 'Quote body',
                   'Header', 'Next', 'One', 'Two', 'checked Complete', 'unchecked Pending',
                   'Footnotes and repeated.', 'Footnote One footnote only. Continuation of the footnote.',
                   'f("<tag>") # code comment', '<!-- visible in code -->', '%%also code%%',
                   '<!-- literal -->', 'Escaped * and [literal] and $4.', 'is silent.', 'Unresolved note')
        offset = 0
        for phrase in ordered:
            offset = output.index(phrase, offset) + len(phrase)
        for hidden in ('Frontmatter secret', 'snoopy-died', 'Image secret', 'image-target.jpg',
                       'hidden-reference', 'Hidden title', 'Collapsed secret', 'secret-link',
                       'Hidden HTML', 'hidden Obsidian', r'\frac', 'hidden query', 'dv.io', 'Cycle'):
            self.assertNotIn(hidden, output)
        self.assertEqual(output.count('One footnote only.'), 1)
        spoken = [text.strip() for text, _, _ in utterances(output, breaks=prepared.breaks)]
        for part in ('Header', 'Next', 'One', 'Two', 'checked Complete', 'unchecked Pending',
                     'f("<tag>") # code comment', '<!-- visible in code -->'):
            self.assertIn(part, spoken)
        for phrase in ('😀 Heading', 'image.jpg', 'Technology', 'Two', 'Complete', 'visible in code', 'Unresolved note'):
            start, end = phrase_range(prepared, phrase)
            mapped = prepared.source_range(start, end)
            self.assertEqual(portion(MIXED, *mapped), phrase)
            if phrase != 'Complete':
                self.assertEqual(prepared.speech_position(mapped[0]), start)

    def test_literal_and_entity_offsets_and_mixed_line_endings(self):
        source = '# 😀 text\r\n\r\nA &amp; B \\* `a!=b` and [x][r].\r\n\r\n[r]: target\r\n'
        prepared = prepare_markdown(source)
        for spoken, raw in (('😀 text', '😀 text'), ('&', '&amp;'), ('*', '*'),
                            ('a!=b', 'a!=b'), ('x', 'x')):
            mapped = prepared.source_range(*phrase_range(prepared, spoken))
            self.assertEqual(portion(source, *mapped), raw)

    def test_rendered_cues_and_emoji_preserve_utf16(self):
        prepared = prepare_rendered((
            RenderedRun('😀 Header', 3, 'row'), RenderedRun('Last', 24, 'cell'),
            RenderedRun('Done now', 80, 'block', 'checked'),
        ))
        self.assertEqual(prepared.text, '😀 Header Last\n\nchecked Done now')
        self.assertEqual(prepared.source_range(*phrase_range(prepared, 'Header')), (6, 12))
        self.assertEqual(prepared.source_range(*phrase_range(prepared, 'checked')), (80, 84))
        self.assertEqual(prepared.source_range(*phrase_range(prepared, 'Done')), (80, 84))
        self.assertEqual(prepared.speech_position(80), phrase_range(prepared, 'checked')[0])
        self.assertEqual(prepared.speech_position(82), phrase_range(prepared, 'Done')[0] + 2)
        self.assertEqual(prepared.speech_position(40), phrase_range(prepared, 'checked')[0])

    def test_empty_document_can_advance(self):
        prepared = prepare_markdown('![label](file.jpg)\n\n%% hidden %%\n\n```dataview\nLIST\n```')
        self.assertEqual((prepared.text, prepared.breaks), ('', ()))
