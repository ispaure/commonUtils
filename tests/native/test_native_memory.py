"""Native subscriptions suppress queued work after disposal or owner collection."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import gc
from types import SimpleNamespace
import unittest
import weakref
from commonUtils.ui.native.memory import MemoryPressure


class NativeMemoryTests(unittest.TestCase):
    def host(self):
        class Host:
            def __init__(self):
                self._impl = SimpleNamespace()
                self.queued, self.calls = [], []
                self.loop = SimpleNamespace(call_soon_threadsafe=self.queued.append)
            def release(self): self.calls.append('pressure')
            def changed(self): self.calls.append('configuration')
        return Host()

    def test_delivery_and_queued_disposal(self):
        app = self.host()
        subscription = MemoryPressure(app, on_pressure=app.release, on_configuration=app.changed)
        subscription.release()
        subscription.dispatch('configuration')
        for callback in app.queued: callback()
        self.assertEqual(app.calls, ['pressure', 'configuration'])
        app.queued.clear()
        subscription.release()
        subscription.dispose()
        subscription.dispose()
        app.queued.pop()()
        subscription.release()
        self.assertEqual(app.calls, ['pressure', 'configuration'])
        self.assertFalse(app.queued)

    def test_bound_callbacks_do_not_keep_host_alive(self):
        app = self.host()
        reference = weakref.ref(app)
        subscription = MemoryPressure(app, on_pressure=app.release)
        del app
        gc.collect()
        self.assertIsNone(reference())
        subscription.release()
        subscription.dispose()
