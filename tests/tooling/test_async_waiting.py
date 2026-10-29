"""Polling preserves failures, cancellation and stable native acknowledgement."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.SMOKE
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from commonUtils.testing import waiting


class AsyncWaitingTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_delay_cannot_turn_late_readiness_into_a_pass(self):
        state = {'time': 0}
        async def oversleep(delay):
            state['time'] = 2
        with patch.object(waiting, 'monotonic', side_effect=lambda: state['time']), \
                patch.object(waiting.asyncio, 'sleep', side_effect=oversleep):
            with self.assertRaisesRegex(AssertionError, 'deadline'):
                await waiting.wait_until(lambda: state['time'] > 1, timeout=1, message='deadline')

    async def test_late_assertion_success_preserves_previous_failure(self):
        state = {'time': 0}
        async def oversleep(delay):
            state['time'] = 2
        def check():
            if state['time'] == 0:
                raise AssertionError('still outside safe area')
            return True
        with patch.object(waiting, 'monotonic', side_effect=lambda: state['time']), \
                patch.object(waiting.asyncio, 'sleep', side_effect=oversleep):
            with self.assertRaisesRegex(AssertionError, 'still outside safe area'):
                await waiting.wait_for_assertion(check, timeout=1)

    async def test_ready_value_is_returned_without_sleeping(self):
        with patch.object(waiting.asyncio, 'sleep', new_callable=AsyncMock) as sleep:
            self.assertEqual(await waiting.wait_until(lambda: {'ready': True}), {'ready': True})
        sleep.assert_not_awaited()

    async def test_deadline_keeps_final_diagnostics_and_bounds_last_sleep(self):
        message = Mock(return_value='last state: loading')
        with patch.object(waiting, 'monotonic', side_effect=[0, .96, .96, 1]), \
                patch.object(waiting.asyncio, 'sleep', new_callable=AsyncMock) as sleep:
            with self.assertRaisesRegex(AssertionError, 'last state: loading'):
                await waiting.wait_until(lambda: False, timeout=1, message=message)
        self.assertAlmostEqual(sleep.await_args.args[0], .04)
        message.assert_called_once_with()

    async def test_polling_never_swallows_unexpected_errors_or_cancellation(self):
        for error in (ValueError('broken bridge'), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)):
                    await waiting.wait_until(Mock(side_effect=error))

    async def test_transient_assertion_is_rechecked_and_persistent_one_is_preserved(self):
        with patch.object(waiting.asyncio, 'sleep', new_callable=AsyncMock):
            self.assertEqual(await waiting.wait_for_assertion(
                Mock(side_effect=[AssertionError('moving'), 4])), 4)
        final = AssertionError('control outside safe area')
        with patch.object(waiting, 'monotonic', side_effect=[0, 1]):
            with self.assertRaises(AssertionError) as caught:
                await waiting.wait_for_assertion(Mock(side_effect=final), timeout=1)
        self.assertIs(caught.exception, final)

    async def test_assertion_wait_does_not_retry_programming_errors(self):
        check = Mock(side_effect=AttributeError('missing control'))
        with self.assertRaises(AttributeError):
            await waiting.wait_for_assertion(check)
        check.assert_called_once_with()

    async def test_invalid_budgets_fail_before_observing_the_ui(self):
        check = Mock()
        for values in ({'timeout': 0}, {'timeout': float('nan')}, {'interval': -1}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                await waiting.wait_until(check, **values)
        check.assert_not_called()
