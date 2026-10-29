"""Weak subscribers coalesce independently and preserve pre-wait notifications."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import gc
import unittest
from commonUtils.runtime.signals import CoalescedSignal


class CoalescedSignalTests(unittest.IsolatedAsyncioTestCase):
    async def test_independent_subscribers_bursts_and_retirement(self):
        signal = CoalescedSignal()
        first, second = signal.waiter(), signal.waiter(initial=False)
        await first()
        pending = asyncio.create_task(second())
        await asyncio.sleep(0)
        self.assertFalse(pending.done())
        for _ in range(100):
            signal.notify()
        await pending
        await first()
        pending = asyncio.create_task(first())
        await asyncio.sleep(0)
        self.assertFalse(pending.done())
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        del pending, first, second
        await asyncio.sleep(0)
        gc.collect()
        self.assertEqual(len(signal._listeners), 0)
