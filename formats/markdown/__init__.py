"""Portable Markdown properties; readers and widgets live under ui."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from .properties import (Frontmatter, RawYAML, split_frontmatter, parse_property_value,
                         parse_properties, replace_property, replace_frontmatter)


def link_path_names(path):
    """Try one URL decode before the literal local Markdown path."""
    from urllib.parse import unquote
    return tuple(dict.fromkeys((unquote(path), path)))
