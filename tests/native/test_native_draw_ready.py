"""Draw acknowledgements, timeout and cancellation retire native listeners."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch
from commonUtils.ui.native.draw_ready import wait_for_draw


class DrawReadyTests(IsolatedAsyncioTestCase):
    async def test_waits_for_native_ack_then_removes_listener(self):
        calls, callbacks = [], []
        def install(panel, drawn):
            callbacks.append(drawn)
            return lambda: calls.append('removed')
        with patch('commonUtils.ui.native.draw_ready._install_draw_probe', side_effect=install):
            task = asyncio.create_task(wait_for_draw(SimpleNamespace()))
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            callbacks[0]()
            self.assertTrue(await task)
        self.assertEqual(calls, ['removed'])

    async def test_timeout_and_cancel_retire_late_callbacks(self):
        for cancel in (False, True):
            calls, callbacks = [], []
            def install(panel, drawn):
                callbacks.append(drawn)
                return lambda: calls.append('removed')
            with patch('commonUtils.ui.native.draw_ready._install_draw_probe', side_effect=install):
                task = asyncio.create_task(wait_for_draw(SimpleNamespace(), timeout=.01))
                await asyncio.sleep(0)
                if cancel:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                else:
                    self.assertFalse(await task)
                callbacks[0]()
                await asyncio.sleep(0)
            self.assertEqual(calls, ['removed'])
