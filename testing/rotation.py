"""Native Toga orientation requests, independent of application navigation.

iOS acknowledgement observes the exact interface orientation. Android observes
the configuration and window aspect; this does not certify left/right direction
on devices whose firmware constrains rotation. Scenario assertions own layout
and content readiness after native acknowledgement.
"""
from contextlib import asynccontextmanager

from ..runtime.platform import get_os

from .settings import ROTATION_TIMEOUT
from .waiting import wait_until

# name: (UIKit mask, UIKit interface orientation, Android requested orientation,
#        Android configuration orientation)
ORIENTATIONS = {
    'portrait': (2, 1, 1, 1),
    'portrait-upside-down': (4, 2, 9, 1),
    'landscape-left': (8, 3, 0, 2),
    'landscape-right': (16, 4, 8, 2),
}


class NativeRotation:
    def __init__(self, window, *, activity=None, platform=None):
        self.window = window
        self.activity = activity
        self.platform = get_os().value.lower() if platform is None else platform
        if self.platform not in {'ios', 'android'}:
            raise ValueError('Native rotation requires iOS or Android')
        if self.platform == 'android' and activity is None:
            raise ValueError('Android rotation requires an Activity')
        self.errors = []
        self._rejection = None

    def request(self, orientation, *, on_rejected=None):
        mask, _, android, _ = ORIENTATIONS[orientation]
        self.errors.clear()
        if self.platform == 'ios':
            from rubicon.objc import Block, ObjCClass, ObjCInstance, objc_id
            preferences = ObjCClass('UIWindowSceneGeometryPreferencesIOS').alloc().initWithInterfaceOrientations(mask)

            def rejected(error):
                message = str(ObjCInstance(error))
                self.errors.append(message)
                if on_rejected is not None:
                    on_rejected(message)

            # Retain the callback throughout asynchronous native acknowledgement.
            self._rejection = Block(rejected, None, objc_id)
            self.window._impl.native.windowScene.requestGeometryUpdateWithPreferences(
                preferences, errorHandler=self._rejection)
        else:
            self.activity.setRequestedOrientation(android)

    def acknowledged(self, orientation):
        _, ios, _, configuration = ORIENTATIONS[orientation]
        if self.errors:
            raise AssertionError('Native rotation rejected: ' + orientation + '; ' + '; '.join(self.errors))
        if self.platform == 'ios':
            return int(self.window._impl.native.windowScene.interfaceOrientation) == ios
        configured = int(self.activity.getResources().getConfiguration().orientation)
        landscape = self.window.size.width > self.window.size.height
        return configured == configuration and landscape == (configuration == 2)

    async def rotate(self, orientation, *, timeout=ROTATION_TIMEOUT, on_rejected=None):
        self.request(orientation, on_rejected=on_rejected)
        await wait_until(lambda: self.acknowledged(orientation), timeout=timeout,
                         message='Native rotation did not complete: ' + orientation)

    @asynccontextmanager
    async def restored(self):
        """Restore the original orientation policy even when a scenario fails.

        Android's original policy may be sensor-driven rather than a fixed pose; restore
        that exact request without claiming it selects one particular final orientation.
        """
        if self.platform == 'android':
            original = self.activity.getRequestedOrientation()
        else:
            current = int(self.window._impl.native.windowScene.interfaceOrientation)
            original = next((name for name, values in ORIENTATIONS.items() if values[1] == current), None)
            if original is None:
                raise AssertionError('Cannot restore an unknown iOS interface orientation: ' + str(current))
        try:
            yield self
        finally:
            if self.platform == 'android':
                self.activity.setRequestedOrientation(original)
            else:
                await self.rotate(original)
