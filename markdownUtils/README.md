# markdownUtils

Dependency-free basic Markdown properties; preserve complex YAML as raw text.

Import from `commonUtils.markdownUtils`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `Frontmatter`, `RawYAML`, `split_frontmatter`, `parse_property_value`, `parse_properties`, `replace_property`, `replace_frontmatter`

[Library overview](../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `RawYAML` | Uninterpreted complex YAML value, retained for display and source editing. |
| `split_frontmatter` | Recognize frontmatter only on the first line; retain its source verbatim. |
| `parse_property_value` | Parse a scalar or simple inline list; return RawYAML for complex syntax. |
| `parse_properties` | Read basic scalar/list fields. Complex values remain RawYAML objects. |
| `replace_property` | Patch one property's lines; preserve all other frontmatter and body text. |
| `replace_frontmatter` | Check the basic mapping structure; retain complex values without interpreting. |
