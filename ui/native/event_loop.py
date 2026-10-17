"""Bind cooperative native dispatch to its owned asyncio loop."""
import asyncio
from asyncio import events


def bind_cooperative_loop(loop):
    """Repair Toga 0.5.7 Android's callback-local running-loop context.

    Java callbacks may enter Python with a different thread state than the one
    used by run_forever_cooperatively. Toga sets the running loop at startup but
    does not restore it around run_delayed_tasks. Own that context for each
    dispatch, while restoring the caller's context when the callback returns.
    """
    if getattr(loop, '_commonutils_bound', False):
        return
    original = getattr(loop, 'run_delayed_tasks', None)
    if original is None:
        return
    asyncio.set_event_loop(loop)
    def dispatch():
        previous = events._get_running_loop()
        events._set_running_loop(loop)
        try:
            return original()
        finally:
            events._set_running_loop(previous)
    loop.run_delayed_tasks = dispatch
    loop._commonutils_bound = True


class DebouncedCallback:
    """Coalesce native text edits on the application's loop (400 ms)."""
    def __init__(self, callback):
        self.callback, self.pending = callback, None

    def __call__(self, *args, **kwargs):
        self.cancel()
        self.pending = asyncio.get_event_loop().call_later(.4, self.run, args, kwargs)

    def run(self, args, kwargs):
        self.pending = None
        self.callback(*args, **kwargs)

    def cancel(self):
        if self.pending is not None:
            self.pending.cancel()
            self.pending = None
