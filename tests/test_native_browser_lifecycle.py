"""Renderer-independent generation, cache-tier and worker retirement checks."""
import asyncio
from threading import Event
from types import SimpleNamespace
import unittest
from commonUtils.ui.native_browser.lifecycle import BrowserLifecycle


class BrowserLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_late_cover_cannot_publish_after_generation_change(self):
        work = BrowserLifecycle()
        started, release = Event(), Event()
        entry = SimpleNamespace(identity='same', revision=1, payload={})
        published = []
        def loader(*args):
            started.set()
            release.wait(5)
            return b'encoded'
        task = work.spawn(work.thumbnail(entry, loader, published.append, epoch=work.epoch, cancelled=work.cancelled))
        await asyncio.to_thread(started.wait, 5)
        work.invalidate()
        self.assertIn(task, work.tasks)
        release.set()
        await work.close()
        self.assertEqual(published, [])
        self.assertFalse(work.tasks)
        self.assertFalse(work.encoded)

    async def test_revision_pruning_and_encoded_cache_bounds_include_decoded_tier(self):
        work = BrowserLifecycle()
        for index in range(70):
            entry = SimpleNamespace(identity=index, revision=1, payload={})
            work.decoded[index, 1] = object()
            await work.thumbnail(entry, lambda *args: b'cover', lambda data: None,
                                 epoch=work.epoch, cancelled=work.cancelled)
        self.assertLessEqual(len(work.encoded), 64)
        self.assertLessEqual(len(work.decoded), 64)
        work.prune({(69, 2)})
        self.assertFalse(work.encoded)
        self.assertFalse(work.decoded)
        await work.close()
