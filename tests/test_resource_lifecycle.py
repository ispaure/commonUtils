"""Resource windows retain cooperative operations through close and resume."""
from types import SimpleNamespace
import unittest
from commonUtils.ui.resources.lifecycle import ResourceOperations


class ResourceLifecycleTests(unittest.TestCase):
    def test_provider_identity_and_closed_generations_reject_late_results(self):
        owner = ResourceOperations()
        first = owner.bind(object())
        self.assertTrue(owner.accepts(first))
        owner.bind(object())
        self.assertFalse(owner.accepts(first))
        current = owner.capture()
        self.assertFalse(owner.stop())
        self.assertFalse(owner.accepts(current))
        owner.resume()
        self.assertTrue(owner.accepts(current))

    def test_close_waits_for_retirement_before_rebind_or_resume(self):
        owner = ResourceOperations()
        calls = []
        job = SimpleNamespace(busy=True, request_cancel=lambda: calls.append('cancel'))
        owner.own(job)
        self.assertTrue(owner.stop())
        self.assertEqual(calls, ['cancel'])
        for action in (owner.resume, lambda: owner.bind(object()), lambda: owner.retire(job)):
            with self.assertRaises(RuntimeError):
                action()
        job.busy = False
        owner.retire(job)
        owner.resume()
        owner.bind(object())
        self.assertFalse(owner.busy)
