"""UI-independent browse entries and a bounded, identity-based navigation tree.

Identities are opaque hashable values. Paths, archives, remote credentials and
widgets belong to adapters; none are required by this module.
"""
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Hashable, Mapping, Callable
from copy import copy


def provider_entries(provider, rows, *, thumbnail=None):
    """Project provider rows once for Qt and native presentations alike."""
    from pathlib import Path
    result = []
    for row in rows:
        relative = provider.relative(row['path'])
        loader = (lambda size, cancelled, path=relative: thumbnail(path, size, cancelled)) if thumbnail and not row['directory'] else None
        result.append(BrowseEntry(provider.root / relative, row['name'], row['directory'],
            {'size': None if row['directory'] else row.get('size'), 'modified': row.get('modified', '')},
            payload=dict(row), revision=row.get('revision'), thumbnail=loader,
            suffix='' if row['directory'] else Path(row['name']).suffix))
    return result


class BrowseRole(IntEnum):
    Identity = 357
    Container = 358
    SortValue = 359
    Thumbnail = 360
    Badge = 361
    Suffix = 362
    Revision = 363


@dataclass(frozen=True)
class BrowseColumn:
    key: str
    label: str
    kind: str = 'text'


@dataclass(frozen=True)
class BrowseEntry:
    identity: Hashable
    label: str
    container: bool = False
    properties: Mapping = field(default_factory=dict)
    payload: object = None
    revision: object = None
    thumbnail: Callable | None = None
    badge: object = ''
    suffix: str = ''


class BrowseTree:
    """Cached listings with stable identities; suitable for native and Qt adapters."""
    def __init__(self, root: BrowseEntry, *, max_entries=10000):
        if not root.container:
            raise ValueError('The browsing root must contain children.')
        if root.identity is None:
            raise ValueError('None is reserved for a missing identity.')
        hash(root.identity)
        self.root = root.identity
        self.max_entries = max_entries
        self.entries = {root.identity: root}
        self.parents = {root.identity: None}
        self.children = {}

    def within(self, identity, scope):
        while identity is not None:
            if identity == scope:
                return True
            identity = self.parents.get(identity)
        return False

    def ensure(self, entry, parent):
        """Install a known ancestor without claiming its listing is complete."""
        if entry.identity is None:
            raise ValueError('None is reserved for a missing identity.')
        hash(entry.identity)
        if parent not in self.entries or not self.entries[parent].container:
            raise ValueError('Unknown parent container.')
        if entry.identity in self.entries:
            if self.parents[entry.identity] != parent:
                raise ValueError('An identity cannot belong to two parents.')
            return
        if len(self.entries) >= self.max_entries:
            raise ValueError('Browsing entry limit exceeded.')
        self.entries[entry.identity] = entry
        self.parents[entry.identity] = parent

    def set_children(self, parent, entries):
        entries = tuple(entries)
        if parent not in self.entries or not self.entries[parent].container:
            raise ValueError('Unknown parent container.')
        identities = set()
        for entry in entries:
            if entry.identity is None:
                raise ValueError('None is reserved for a missing identity.')
            hash(entry.identity)
            if entry.identity in identities or self.within(parent, entry.identity):
                raise ValueError('Duplicate or cyclic browsing identity.')
            if entry.identity in self.parents and self.parents[entry.identity] != parent:
                raise ValueError('An identity cannot belong to two parents.')
            identities.add(entry.identity)
        removed = {identity for identity, ancestor in self.parents.items()
                   if ancestor == parent and identity not in identities}
        # A changed container invalidates its cached descendants.
        removed.update(entry.identity for entry in entries
                       if entry.identity in self.entries and
                       (not entry.container or entry.revision != self.entries[entry.identity].revision))
        def invalidated(identity):
            while identity is not None and identity != parent:
                if identity in removed:
                    return True
                identity = self.parents.get(identity)
            return False
        discard = {identity for identity in self.entries if invalidated(identity)}
        if len(self.entries) - len(discard) + len(identities - (self.entries.keys() - discard)) > self.max_entries:
            raise ValueError('Browsing entry limit exceeded.')
        for identity in discard:
            self.entries.pop(identity, None)
            self.parents.pop(identity, None)
            self.children.pop(identity, None)
        for entry in entries:
            self.entries[entry.identity] = entry
            self.parents[entry.identity] = parent
        self.children[parent] = tuple(entry.identity for entry in entries)

    def updated_children(self, parent, entries):
        """Validate a new snapshot before a UI begins structural notifications."""
        updated = copy(self)
        updated.entries = dict(self.entries)
        updated.parents = dict(self.parents)
        updated.children = dict(self.children)
        updated.set_children(parent, entries)
        return updated


class BrowseHistory:
    """Bounded navigation locations; adapters own resolving and loading them."""
    def __init__(self, max_locations=100):
        if max_locations < 2:
            raise ValueError('History needs at least two locations.')
        self.max_locations = max_locations
        self.locations = []

    @property
    def current(self):
        return self.locations[-1] if self.locations else None

    def visit(self, location):
        if location != self.current:
            self.locations.append(location)
            del self.locations[:-self.max_locations]

    def previous(self):
        return self.locations[-2] if len(self.locations) > 1 else None

    def clear(self):
        self.locations.clear()


def query_entries(entries, text='', *, sort='name', descending=False):
    """Filter a supplied folder snapshot; sort groups while retaining folders first."""
    import re
    from ..search.names import search_terms, matches_name
    terms = search_terms(text)
    rows = [entry for entry in entries if matches_name(entry.label, terms)]
    def name_key(entry):
        return tuple((1, int(part)) if part.isdigit() else (0, part.casefold())
                     for part in re.split(r'(\d+)', entry.label))
    def key(entry):
        if sort == 'size':
            value = entry.properties.get('size')
            return (value if isinstance(value, (float, int)) else -1, name_key(entry))
        if sort == 'modified':
            return str(entry.properties.get('modified') or ''), name_key(entry)
        if sort != 'name':
            raise ValueError('Unknown sort field.')
        return name_key(entry)
    return sorted((entry for entry in rows if entry.container), key=key, reverse=descending) + sorted(
        (entry for entry in rows if not entry.container), key=key, reverse=descending)
