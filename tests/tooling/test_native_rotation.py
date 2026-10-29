"""Native orientation mechanisms with fake platform bridges; no device proof."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.SMOKE
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from commonUtils.testing.rotation import NativeRotation
from commonUtils.testing import waiting


class NativeRotationTests(unittest.IsolatedAsyncioTestCase):
    def android(self, *, configuration=1, width=400, height=800, original=-1):
        self.configuration = NS(orientation=configuration)
        self.activity = Mock()
        self.activity.getResources.return_value.getConfiguration.return_value = self.configuration
        self.activity.getRequestedOrientation.return_value = original
        self.window = NS(size=NS(width=width, height=height))
        return NativeRotation(self.window, activity=self.activity, platform='android')

    async def test_android_requires_configuration_and_window_to_agree(self):
        rotation = self.android(configuration=1, width=800, height=400)
        rotation.request('landscape-right')
        self.activity.setRequestedOrientation.assert_called_once_with(8)
        self.assertFalse(rotation.acknowledged('landscape-right'))
        self.configuration.orientation = 2
        self.assertTrue(rotation.acknowledged('landscape-right'))
        self.window.size.width = 300
        self.assertFalse(rotation.acknowledged('landscape-right'))

    async def test_android_restores_sensor_policy_after_scenario_failure(self):
        rotation = self.android(original=-1)
        with self.assertRaisesRegex(RuntimeError, 'scenario failed'):
            async with rotation.restored():
                rotation.request('landscape-left')
                raise RuntimeError('scenario failed')
        self.assertEqual(self.activity.setRequestedOrientation.call_args_list[-1].args, (-1,))

    async def test_unacknowledged_request_fails_at_its_budget(self):
        rotation = self.android()
        with patch.object(waiting, 'monotonic', side_effect=[0, 1]), \
                patch.object(waiting.asyncio, 'sleep', new_callable=AsyncMock):
            with self.assertRaisesRegex(AssertionError, 'Native rotation did not complete: landscape-left'):
                await rotation.rotate('landscape-left', timeout=1)

    async def test_ios_restores_original_pose_after_scenario_failure(self):
        window = NS(_impl=NS(native=NS(windowScene=NS(interfaceOrientation=4))))
        rotation = NativeRotation(window, platform='ios')
        with patch.object(rotation, 'rotate', new_callable=AsyncMock) as restore:
            with self.assertRaisesRegex(RuntimeError, 'scenario failed'):
                async with rotation.restored():
                    raise RuntimeError('scenario failed')
        restore.assert_awaited_once_with('landscape-right')

    async def test_ios_rejection_is_reported_and_callback_is_retained(self):
        scene = Mock(interfaceOrientation=1)
        window = NS(_impl=NS(native=NS(windowScene=scene)))
        rotation = NativeRotation(window, platform='ios')
        bridge = NS(Block=lambda callback, *args: callback, ObjCClass=Mock(),
                    ObjCInstance=lambda error: error, objc_id=object())
        rejected = Mock()
        with patch.dict('sys.modules', {'rubicon.objc': bridge}):
            rotation.request('landscape-left', on_rejected=rejected)
        self.assertFalse(rotation.acknowledged('landscape-left'))
        callback = scene.requestGeometryUpdateWithPreferences.call_args.kwargs['errorHandler']
        self.assertIs(callback, rotation._rejection)
        callback('unsupported pose')
        rejected.assert_called_once_with('unsupported pose')
        with self.assertRaisesRegex(AssertionError, 'unsupported pose'):
            rotation.acknowledged('landscape-left')

    async def test_ios_acknowledges_direction_without_assuming_aspect(self):
        scene = NS(interfaceOrientation=3)
        rotation = NativeRotation(NS(_impl=NS(native=NS(windowScene=scene))), platform='ios')
        self.assertTrue(rotation.acknowledged('landscape-left'))
        self.assertFalse(rotation.acknowledged('landscape-right'))

    async def test_unsupported_host_and_unknown_pose_fail_without_dispatch(self):
        with self.assertRaises(ValueError):
            NativeRotation(object(), platform='darwin')
        rotation = self.android()
        with self.assertRaises(KeyError):
            rotation.request('diagonal')
        self.activity.setRequestedOrientation.assert_not_called()
