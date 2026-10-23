# Markdown text helpers

Dependency-free basic Markdown properties; preserve complex YAML as raw text.

Import from `commonUtils.formats.markdown`. Implementation and public exports live in
[`properties.py`](../../../../formats/markdown/properties.py).

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
