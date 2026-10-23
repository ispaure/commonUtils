"""Portable literal text queries; no UI, storage or regular-expression backend policy."""
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
