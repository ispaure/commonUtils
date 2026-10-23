import threading
import unittest

from commonUtils.runtime.resources.lifetime import ResourceLeases, WorkerCancellation


class ResourceLifetimeTests(unittest.TestCase):
    def test_last_owner_closes_once_even_with_concurrent_duplicate_release(self):
        calls = []
        leases = ResourceLeases(validate=lambda: calls.append('validate'), close=lambda: calls.append('close'))
        first, second = leases.acquire(), leases.acquire()
        first('ignored UI argument')
        self.assertEqual(calls, ['validate', 'validate'])
        workers = [threading.Thread(target=second) for _ in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(calls, ['validate', 'validate', 'close'])

    def test_failed_validation_does_not_acquire_an_owner(self):
        calls = []
        active = False
        def validate():
            if not active:
                raise ValueError('closed')
        leases = ResourceLeases(validate=validate, close=lambda: calls.append('close'))
        with self.assertRaises(ValueError):
            leases.acquire()
        active = True
        leases.acquire()()
        self.assertEqual(calls, ['close'])

    def test_failed_close_cannot_release_same_owner_twice(self):
        calls = []
        def close():
            calls.append('close')
            raise ValueError('cleanup failed')
        release = ResourceLeases(validate=lambda: None, close=close).acquire()
        with self.assertRaises(ValueError):
            release()
        release()
        self.assertEqual(calls, ['close'])

    def test_nested_cancellation_restores_on_error_and_is_worker_local(self):
        cancellation = WorkerCancellation()
        parent = threading.Event()
        other = []
        with cancellation.scope(parent.is_set):
            outer = cancellation.current
            with self.assertRaises(ValueError):
                with cancellation.scope(lambda: True):
                    captured = cancellation.current
                    self.assertTrue(captured())
                    worker = threading.Thread(target=lambda: other.append(cancellation.current()))
                    worker.start()
                    worker.join()
                    raise ValueError('worker failed')
            self.assertIs(cancellation.current, outer)
            self.assertFalse(outer())
            parent.set()
            self.assertTrue(outer())
        self.assertFalse(cancellation.current())
        self.assertEqual(other, [False])
        self.assertTrue(captured())


if __name__ == '__main__':
    unittest.main()
