"""Weak, coalescing asynchronous broadcasts on one owning event loop."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

import asyncio
from weakref import WeakSet


class CoalescedSignal:
    """Each waiter observes a burst once; idle subscribers require no timer.

    Create and notify subscribers on the owning loop thread. A waiter closure
    owns its event; the signal never retains the subscriber or its owner. Cancel
    in-flight waits when retiring the task, then release the waiter closure.
    """
    def __init__(self):
        self._listeners = WeakSet()

    def waiter(self, *, initial=True):
        event = asyncio.Event()
        if initial:
            event.set()
        self._listeners.add(event)

        async def changed():
            await event.wait()
            event.clear()
        return changed

    def notify(self):
        for event in tuple(self._listeners):
            event.set()
