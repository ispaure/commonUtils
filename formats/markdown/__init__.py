"""Portable Markdown properties; readers and widgets live under ui."""
from .properties import (Frontmatter, RawYAML, split_frontmatter, parse_property_value,
                         parse_properties, replace_property, replace_frontmatter)


def link_path_names(path):
    """Try one URL decode before the literal local Markdown path."""
    from urllib.parse import unquote
    return tuple(dict.fromkeys((unquote(path), path)))
