"""Immutable archive metadata; importing this module requires no GUI."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    name: str
    size: int
    packed: int | None
    directory: bool
    modified: str
    encrypted: bool = False
