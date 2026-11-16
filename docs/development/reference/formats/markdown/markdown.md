# Markdown text helpers

Dependency-free basic Markdown properties; preserve complex YAML as raw text.

Import from `commonUtils.formats.markdown`. Implementation and public exports live in
[`properties.py`](../../../../../formats/markdown/properties.py).

Public entry points: `Frontmatter`, `RawYAML`, `split_frontmatter`, `parse_property_value`, `parse_properties`, `replace_property`, `replace_frontmatter`

[Library overview](../../../overview.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `RawYAML` | Uninterpreted complex YAML value, retained for display and source editing. |
| `split_frontmatter` | Recognize frontmatter only on the first line; retain its source verbatim. |
| `parse_property_value` | Parse a scalar or simple inline list; return RawYAML for complex syntax. |
| `parse_properties` | Read basic scalar/list fields. Complex values remain RawYAML objects. |
| `replace_property` | Patch one property's lines; preserve all other frontmatter and body text. |
| `replace_frontmatter` | Check the basic mapping structure; retain complex values without interpreting. |

## Module owners

- `properties.py`: frontmatter parsing and preservation; the package exports the established property names.
- `images.py`: portable image-size hints.
- `wiki.py`: Markdown catalogs, landing pages, link resolution and library search.
- `file.py`: registered MarkdownFile type with lazy reader activation.

Presentation remains in `ui.markdown` and `ui.native`. Shared query mechanics live in [search](../../search/search.md).

Wiki traversal uses the shared portable junction query rather than requiring
Python 3.12 pathlib methods. GUI-free catalog tests live in
`tests/markdown/test_wiki_catalog.py`; Qt navigation tests remain in their viewer owner.

## Live editing syntax

`formats.markdown.editing` owns `InlineSpan`, `inline_spans`, `HEADING`,
`FENCE_OPEN`, `fence_close` and `SELECTION_MARKERS` without importing a UI toolkit.
The Qt Markdown adapter uses these definitions for display and export.
`web_patterns()` exports the inline patterns with JavaScript named captures and
Unicode character classes, plus the heading pattern and selection delimiters.
The `active` entry contains the web adapter functions `syntaxActive` and
`liveSpans`; hosts compile inline patterns with `gu` flags and insert this adapter
beside those patterns. Code payload protection and incomplete-backtick handling
live beside the native parser rather than in each consuming application.

`syntax_active(start, end, first, last)` owns the native interval predicate.
A collapsed caret reveals syntax at either endpoint or inside an interval; a
selection must strictly overlap it. Offsets use the caller's units (Qt and DOM
use UTF-16). Headings use the whole heading interval; inline markers use their
own span. The web adapter implements the same predicate, with consumer browser
regressions comparing its results to `syntax_active`, including emoji offsets.
WebView hosts own DOM interaction, selection positions, composition and undo.
These helpers do not implement a complete CommonMark parser.

## Read-aloud preparation

Use `formats.markdown.speech.prepare_markdown(markdown)` when the caller already
holds authorized Markdown. It uses the offline Markdown parser and keeps link
labels, task states, footnote bodies and code while skipping image markup,
hidden comments, frontmatter and data-view source. It performs no provider
access and has no query or embed resolver. Unresolved note embeds contribute
their labels. Supply rendered content if a host has expanded an embed or
published a generated view.

Use `prepare_rendered(runs)` with ordered `RenderedRun` values from the visible
document. Qt passes text fragments and their cursor positions. The mobile
adapter passes selected or visible DOM text and coordinates. Include visible
table captions and cells, accessible math labels, and already-resolved embed or
generated content when available. Exclude hidden nodes and image alt text.
Boundary values are `line`, `cell`, `row` and `block`. A run can also carry a
cue such as `checked` or `Footnote` anchored to the first visible word.

```python
from commonUtils.formats.markdown.speech import prepare_markdown
from commonUtils.runtime.speech import utterances

prepared = prepare_markdown("# Heading\n\n[Label](destination)")
payload = list(utterances(prepared.text, breaks=prepared.breaks))
assert payload[0][0] == "Heading"
assert prepared.source_range(0, 7) == (2, 9)
```

Positions and hard breaks use UTF-16 code units. `source_range(start, end)`
maps a speech callback to the original Markdown or rendered coordinate space.
`speech_position(source_position)` maps the other way and advances across
hidden markup. Inserted breaks and unavailable source fragments have no
highlight. For transformed text such as HTML entities, the mapping covers the
source token. The caller owns authorization, snapshot lifetime, playback,
the visibility of rendered nodes, and discarding mappings after a view refresh.
