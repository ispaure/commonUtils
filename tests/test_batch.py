"""Portable batch outcomes and cancellation without importing a UI toolkit."""
from threading import Event
import unittest
from commonUtils.runtime.operations import run_batch


class BatchTests(unittest.TestCase):
    def test_successful_unhashable_items_do_not_require_failure_dictionary_keys(self):
        items = [{'path': 'first'}, {'path': 'second'}]
        for stop_on_error in (False, True):
            with self.subTest(stop_on_error=stop_on_error):
                result = run_batch(items, lambda item: True, stop_on_error=stop_on_error)
                self.assertEqual(result.completed, items)
                self.assertEqual(result.failed, {})
                self.assertEqual(result.remaining, [])
                self.assertFalse(result.cancelled)

    def test_batch_errors_do_not_prevent_later_items_and_cancel_waits_for_item(self):
        cancel = Event()
        def work(item):
            if item == 'bad':
                raise OSError('read failed')
            cancel.set()
            return True
        result = run_batch(['bad', 'good', 'untouched'], work, cancelled=cancel.is_set)
        self.assertEqual(result.completed, ['good'])
        self.assertEqual(result.failed, {'bad': 'read failed'})
        self.assertEqual(result.remaining, ['untouched'])
        self.assertTrue(result.cancelled)

    def test_stop_on_error_preserves_remaining_selection(self):
        result = run_batch(['bad', 'untouched'], lambda item: False, stop_on_error=True)
        self.assertEqual(result.remaining, ['untouched'])
        self.assertFalse(result.cancelled)
        self.assertFalse(result)
