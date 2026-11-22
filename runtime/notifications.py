"""Toolkit-independent notices and one-shot completion eligibility."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from dataclasses import dataclass
from time import monotonic
from uuid import uuid4


@dataclass(frozen=True)
class Notice:
    id: str
    source: str
    title: str
    message: str
    outcome: str = 'success'
    activate: object = None
    native: bool = False


class Completion:
    """One run's terminal event. Call on the presentation owner's thread."""

    def __init__(self, minimum_seconds, *, clock=monotonic):
        self._minimum_seconds = minimum_seconds
        self._clock = clock
        self._started = clock()
        self._identifier = uuid4().hex
        self._finished = False

    def finish(self, source, title, message, *, outcome, observed=False):
        """Return a notice once for an eligible success or failure."""
        if self._finished:
            return None
        self._finished = True
        if observed or outcome not in ('success', 'failure'):
            return None
        if self._clock() - self._started < self._minimum_seconds:
            return None
        return Notice(self._identifier, source, title, message, outcome)
