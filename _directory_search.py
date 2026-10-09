"""Shared filename-query rules for SQLite snapshots and in-memory snapshots.

Bare terms are case-insensitive substrings joined with AND. Quoted phrases keep
adjacent word order, treating whitespace, underscores and hyphens as separators.
Wildcards and SQL punctuation remain literal. An unfinished quote is a phrase so
live search remains predictable while typing.
"""
import re

_TOKENS = re.compile(r'"([^"]*)(?:"|$)|([^\s"]+)')
_SEPARATORS = re.compile(r'[\s_-]+')


def search_words(name):
    return _SEPARATORS.sub(' ', name.casefold()).strip()


def search_terms(query):
    terms = []
    for match in _TOKENS.finditer(query):
        phrase, keyword = match.groups()
        value = search_words(phrase) if phrase is not None else keyword.casefold()
        if value:
            terms.append((value, phrase is not None))
    return tuple(terms)


def search_sql(query):
    terms = search_terms(query)
    clauses = ['instr(search_words(name_fold),?)>0' if phrase else 'instr(name_fold,?)>0'
               for value, phrase in terms]
    return (' AND '.join(clauses) or '1'), tuple(value for value, phrase in terms)


def matches_name(name, terms):
    folded = name.casefold()
    normalized = search_words(folded) if any(phrase for _, phrase in terms) else ''
    return all(value in (normalized if phrase else folded) for value, phrase in terms)
