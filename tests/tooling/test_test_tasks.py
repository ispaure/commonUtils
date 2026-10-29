"""Repeated lifecycle entry retains the original task and its failure."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.SMOKE
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from commonUtils.testing.tasks import start_once


class StartOnceTests(unittest.IsolatedAsyncioTestCase):
    async def test_running_and_completed_task_is_never_started_again(self):
        owner = SimpleNamespace()
        loop = asyncio.get_running_loop()
        result = loop.create_future()

        async def exercise():
            return await result

        factory = Mock(side_effect=exercise)
        first = start_once(owner, factory, loop=loop)
        self.assertIs(start_once(owner, factory, loop=loop), first)
        result.set_result('finished')
        self.assertEqual(await first, 'finished')
        self.assertIs(start_once(owner, factory, loop=loop), first)
        factory.assert_called_once_with()

    async def test_failed_task_is_retained_and_other_owner_is_independent(self):
        loop = asyncio.get_running_loop()
        owner, other = SimpleNamespace(), SimpleNamespace()

        async def exercise():
            raise RuntimeError('native check failed')

        failed = start_once(owner, exercise, loop=loop)
        with self.assertRaisesRegex(RuntimeError, 'native check failed'):
            await failed
        self.assertIs(start_once(owner, exercise, loop=loop), failed)
        separate = start_once(other, exercise, loop=loop)
        self.assertIsNot(separate, failed)
        with self.assertRaises(RuntimeError):
            await separate
