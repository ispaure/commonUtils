
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from time import monotonic
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operations import ResultWorker


class ResultWorkerTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_owner_gets_redacted_error_after_retirement(self):
        class Cancelled(Exception):
            pass
        def work():
            raise Cancelled('secret')
        worker = ResultWorker(work, error_formatter=lambda error: 'redacted', cancellation_errors=(Cancelled,))
        finished = []
        worker.finished.connect(lambda: finished.append(not worker.isRunning()))
        worker.start()
        deadline = monotonic() + 3
        while not finished and monotonic() < deadline:
            self.app.processEvents()
        worker.wait()
        self.assertEqual(finished, [True])
        self.assertEqual(worker.error, 'redacted')
        self.assertTrue(worker.cancelled)

    def test_empty_or_invalid_formatted_errors_remain_visible_without_secret_fallback(self):
        for formatter in (lambda error: '', lambda error: '  ', lambda error: None):
            with self.subTest(formatter=formatter):
                def fail():
                    raise RuntimeError('sensitive underlying details')
                worker = ResultWorker(fail, error_formatter=formatter)
                worker.run()
                self.assertIsInstance(worker.error, str)
                self.assertTrue(worker.error.strip())
                self.assertNotIn('sensitive', worker.error)

    def test_formatter_failure_does_not_escape_or_reveal_unredacted_details(self):
        def fail():
            raise RuntimeError('sensitive underlying details')
        def formatting(error):
            raise ValueError('sensitive formatter details')
        worker = ResultWorker(fail, error_formatter=formatting)
        worker.run()
        self.assertIn('RuntimeError', worker.error)
        self.assertNotIn('sensitive', worker.error)

    def test_restarted_worker_clears_prior_result_error_and_cancellation(self):
        class Cancelled(Exception):
            pass
        outcomes = iter(['first', Cancelled('cancelled'), 'last'])
        def work():
            result = next(outcomes)
            if isinstance(result, Exception):
                raise result
            return result
        worker = ResultWorker(work, cancellation_errors=(Cancelled,))
        worker.run()
        self.assertEqual(worker.result, 'first')
        worker.run()
        self.assertIsNone(worker.result)
        self.assertEqual(worker.error, 'cancelled')
        self.assertTrue(worker.cancelled)
        worker.run()
        self.assertEqual(worker.result, 'last')
        self.assertIsNone(worker.error)
        self.assertFalse(worker.cancelled)
