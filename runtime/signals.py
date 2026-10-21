"""Weak, coalescing asynchronous broadcasts on one owning event loop."""
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
