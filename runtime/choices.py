"""Ordered choice identities without widget, selection or persistence policy."""
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar('T')


@dataclass(frozen=True)
class ChoiceOption(Generic[T]):
    id: T
    label: str


class ChoiceSet(Sequence[ChoiceOption[T]]):
    """Immutable option order with unique hashable IDs; None is an ordinary ID.

    Labels may repeat. String-only controls must use from_label(), which rejects
    ambiguity rather than silently dispatching a different identity.
    """
    def __init__(self, options):
        self._options = tuple(options)
        self._positions = {}
        for index, option in enumerate(self._options):
            if option.id in self._positions:
                raise ValueError('Duplicate choice ID: ' + repr(option.id))
            self._positions[option.id] = index

    def __len__(self):
        return len(self._options)

    def __getitem__(self, index):
        return self._options[index]

    @property
    def labels(self):
        return tuple(option.label for option in self._options)

    def index_of(self, identity):
        return self._positions[identity]

    def by_id(self, identity):
        return self._options[self.index_of(identity)]

    def from_label(self, label):
        matches = [option for option in self._options if option.label == label]
        if not matches:
            raise KeyError(label)
        if len(matches) != 1:
            raise ValueError('Ambiguous choice label: ' + repr(label))
        return matches[0]
