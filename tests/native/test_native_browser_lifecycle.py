"""Renderer-independent generation, cache-tier and worker retirement checks."""
import asyncio
from importlib.util import find_spec
from threading import Event
from types import SimpleNamespace
import unittest
from commonUtils.ui.native_browser.lifecycle import BrowserLifecycle

HAS_TOGA = find_spec('toga') is not None


class BrowserLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_stopped_owner_rejects_late_work_and_closes_the_coroutine(self):
        import inspect
        work = BrowserLifecycle()
        work.stop()
        calls = []
        async def late_callback():
            calls.append('ran')
        coroutine = late_callback()
        task = work.spawn(coroutine)
        try:
            self.assertIsNone(task)
            self.assertEqual(inspect.getcoroutinestate(coroutine), inspect.CORO_CLOSED)
            await asyncio.sleep(0)
            self.assertEqual(calls, [])
            self.assertFalse(work.tasks)
        finally:
            await work.close()

    def test_closed_event_loop_rejects_work_without_leaving_an_open_coroutine(self):
        import inspect
        loop = asyncio.new_event_loop()
        loop.close()
        coroutine = asyncio.sleep(0)
        try:
            self.assertIsNone(BrowserLifecycle().spawn(coroutine, loop=loop))
            self.assertEqual(inspect.getcoroutinestate(coroutine), inspect.CORO_CLOSED)
        finally:
            coroutine.close()

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

    @unittest.skipUnless(HAS_TOGA, 'Optional Toga browser backend is not installed')
    async def test_retired_tile_keeps_its_storage_worker_owned_until_close(self):
        from commonUtils.ui.native_browser.recycled import RecycledBrowser
        work = BrowserLifecycle()
        started, release, finished = Event(), Event(), Event()
        cancelled = Event()
        entry = SimpleNamespace(identity='retired', revision=1, payload={})
        published = []
        def loader(*args):
            started.set()
            try:
                if not release.wait(5):
                    raise TimeoutError('Synthetic storage read did not retire')
                return b'cover'
            finally:
                finished.set()
        task = work.spawn(work.thumbnail(entry, loader, published.append,
            epoch=work.epoch, cancelled=cancelled))
        close = None
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 5))
            browser = SimpleNamespace(
                _tile_cards={'retired': (entry, SimpleNamespace(children=[SimpleNamespace(children=[])]),
                                        SimpleNamespace(text='name'), cancelled, task)},
                buttons={'retired': object()}, entry_rows={'retired': object()})
            RecycledBrowser._retire_tile(browser, 'retired')
            self.assertTrue(cancelled.is_set())
            # Let cancellation propagate while storage remains explicitly blocked.
            for _ in range(5):
                await asyncio.sleep(0)
            self.assertIn(task, work.tasks, 'A running storage read lost its owner')
            close = asyncio.create_task(work.close())
            for _ in range(5):
                await asyncio.sleep(0)
            self.assertFalse(close.done(), 'Close released a running storage worker')
            self.assertIn(task, work.tasks)
            self.assertFalse(finished.is_set())
        finally:
            release.set()
            await work.close()
            if close is not None:
                await close
        self.assertTrue(finished.is_set())
        self.assertFalse(work.tasks)
        self.assertEqual(published, [])

    @unittest.skipUnless(HAS_TOGA, 'Optional Toga browser backend is not installed')
    def test_public_browser_exports_retain_presentation_identity(self):
        from commonUtils.ui import native_browser
        from commonUtils.ui.native_browser import presentation
        self.assertIs(native_browser.NativeBrowser, presentation.NativeBrowser)
        self.assertIs(native_browser.clear_box, presentation.clear_box)
        self.assertIs(native_browser.BrowserLifecycle, BrowserLifecycle)

    def test_close_drains_done_tasks_before_their_callbacks_run(self):
        # A subprocess timeout catches a tight event-loop spin without stranding
        # the suite itself. The queued discard callback has deliberately not run.
        import os
        from pathlib import Path
        import subprocess
        import sys
        environment = os.environ.copy()
        environment['PYTHONPATH'] = os.pathsep.join(filter(None, (
            str(Path(__file__).resolve().parents[3]), environment.get('PYTHONPATH'))))
        script = '''
import asyncio
from commonUtils.ui.native_browser.lifecycle import BrowserLifecycle
async def main():
    work = BrowserLifecycle()
    completed = asyncio.get_running_loop().create_future()
    work.retain(completed)
    completed.set_result(None)
    await work.close()
    assert not work.tasks
asyncio.run(main())
'''
        completed = subprocess.run([sys.executable, '-c', script], env=environment,
                                   capture_output=True, text=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
