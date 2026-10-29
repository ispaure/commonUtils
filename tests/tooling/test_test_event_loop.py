"""Fixture cleanup drains cancellation and exposes failed task finalizers."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.SMOKE
import asyncio
import unittest
from threading import Event, Timer

from commonUtils.testing.event_loop import close_loop


class TestLoopCleanupTests(unittest.TestCase):
    def test_executor_timeout_fails_cleanup_instead_of_becoming_only_a_warning(self):
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        started, release, finished = Event(), Event(), Event()

        def worker():
            started.set()
            release.wait(2)
            finished.set()

        loop.create_task(asyncio.to_thread(worker))
        loop.run_until_complete(asyncio.sleep(0))
        self.assertTrue(started.wait(1))
        try:
            with self.assertRaisesRegex(AssertionError, 'executor did not retire'):
                close_loop(loop, timeout=.01)
        finally:
            release.set()
            self.assertTrue(finished.wait(1))

    def test_cancelled_to_thread_finishes_before_storage_can_be_removed(self):
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        started, release, finished = Event(), Event(), Event()

        def worker():
            started.set()
            release.wait(2)
            finished.set()

        loop.create_task(asyncio.to_thread(worker))
        loop.run_until_complete(asyncio.sleep(0))
        self.assertTrue(started.wait(1))
        timer = Timer(.05, release.set)
        timer.start()
        self.addCleanup(timer.join)
        self.addCleanup(release.set)
        close_loop(loop)
        self.assertTrue(finished.is_set())

    def test_pending_task_finally_runs_before_loop_closes(self):
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        retired = []

        async def worker():
            try:
                await asyncio.Event().wait()
            finally:
                retired.append(True)

        loop.create_task(worker())
        loop.run_until_complete(asyncio.sleep(0))
        close_loop(loop)
        self.assertEqual(retired, [True])
        self.assertTrue(loop.is_closed())
        close_loop(loop)  # Cleanup remains safe when another owner already closed it.

    def test_failed_finalizer_is_reported_and_loop_still_closes(self):
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def worker():
            try:
                await asyncio.Event().wait()
            finally:
                raise RuntimeError('fixture did not release its resource')

        loop.create_task(worker())
        loop.run_until_complete(asyncio.sleep(0))
        with self.assertRaisesRegex(RuntimeError, 'did not release'):
            close_loop(loop)
        self.assertTrue(loop.is_closed())
