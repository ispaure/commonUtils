"""One generation, worker-retirement and thumbnail owner for native renderers."""
import asyncio
from collections import OrderedDict
from threading import Event


class BrowserLifecycle:
    def __init__(self):
        self.epoch = 0
        self.cancelled = Event()
        self.tasks = set()
        self.encoded = OrderedDict()
        self.decoded = OrderedDict()
        self.closed = False
        self.slots = None

    def invalidate(self):
        self.epoch += 1
        self.cancelled.set()
        self.cancelled = Event()

    def retain(self, task):
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def spawn(self, coroutine, *, loop=None):
        if self.closed or (loop is not None and loop.is_closed()):
            coroutine.close()
            return None
        try:
            loop = loop or asyncio.get_running_loop()
        except RuntimeError:
            coroutine.close()
            return None
        return self.retain(loop.create_task(coroutine))

    def prune(self, valid):
        for cache in (self.encoded, self.decoded):
            for key in tuple(cache):
                if key not in valid:
                    del cache[key]

    async def thumbnail(self, entry, loader, publish, *, epoch, cancelled):
        if self.slots is None:
            self.slots = asyncio.Semaphore(2)
        async with self.slots:
            if self.closed or cancelled.is_set() or epoch != self.epoch:
                return
            try:
                data = await asyncio.to_thread(loader, entry.payload, (160, 160), cancelled.is_set)
                if data and not self.closed and not cancelled.is_set() and epoch == self.epoch:
                    key = entry.identity, entry.revision
                    self.encoded[key] = data
                    self.encoded.move_to_end(key)
                    while len(self.encoded) > 64 or sum(map(len, self.encoded.values())) > 8 * 1024 * 1024:
                        retired, _ = self.encoded.popitem(last=False)
                        self.decoded.pop(retired, None)
                    if key in self.encoded:
                        publish(data)
            except Exception:
                pass  # An unavailable cover leaves the resource selectable.

    def stop(self):
        self.closed = True
        self.invalidate()
        self.encoded.clear()
        self.decoded.clear()

    async def close(self):
        self.stop()
        while self.tasks:
            tasks = tuple(self.tasks)
            await asyncio.gather(*tasks, return_exceptions=True)
            # gather may finish synchronously for already-completed tasks,
            # before their queued discard callbacks can run on the loop.
            self.tasks.difference_update(tasks)
