"""Portable literal text queries; no UI, storage or regular-expression backend policy."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

import re


def literal_pattern(query, *, case=False):
    """Compile a nonempty literal query, or return None for an empty query.

    Native editors use Python regular-expression case rules. Filename matching
    uses search.names instead; its keyword and phrase grammar is different.
    """
    return re.compile(re.escape(query), 0 if case else re.IGNORECASE) if query else None


def contains_text(text, query, *, case=False):
    """Match a substring, using Unicode casefold for documentation catalogs."""
    return query in text if case else query.casefold() in text.casefold()
