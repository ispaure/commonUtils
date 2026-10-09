"""Shared task progress publishes results on the GUI thread after worker shutdown."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from threading import Event
import time
import unittest
from unittest.mock import patch

from commonUtils.operations import run_batch
from commonUtils.ui import pyside as qt
from commonUtils.ui.operation_progress import OperationProgress
from commonUtils.debugUtils import Severity, log


class BatchTests(unittest.TestCase):
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


class OperationProgressTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.progress = OperationProgress()
        self.addCleanup(self.progress.deleteLater)

    def wait(self):
        deadline = time.monotonic() + 5
        while self.progress.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()

    def test_result_delivered_on_gui_after_worker_shutdown_and_can_restart(self):
        results = []
        def done(value, error):
            self.assertEqual(qt.QThread.currentThread(), self.app.thread())
            self.assertFalse(self.progress.busy)
            self.assertIsNone(self.progress.operation)
            results.append((value, error))
        self.progress.completed.connect(done)
        self.progress.start(lambda report, cancelled: 'first')
        self.wait()
        self.progress.start(lambda report, cancelled: 'second')
        self.wait()
        self.assertEqual(results, [('first', ''), ('second', '')])
        self.assertEqual(self.progress.bar.maximum(), 1000)
        self.assertEqual(self.progress.bar.value(), 1000)
        self.assertEqual(self.progress.message.text(), 'Finished.')

    def test_quiet_operation_keeps_cancellation_and_normal_visibility_default(self):
        entered, release = Event(), Event()
        result = []
        def work(report, cancelled):
            entered.set()
            release.wait(5)
            return cancelled()
        self.progress.completed.connect(lambda value, error: result.append((value, error)))
        self.progress.start(work, show_progress=False)
        try:
            self.assertTrue(entered.wait(2))
            self.assertTrue(self.progress.isHidden())
            self.progress.request_cancel()
            self.assertTrue(self.progress.busy)
        finally:
            release.set()
            self.wait()
        self.assertEqual(result, [(True, '')])
        self.progress.start(lambda report, cancelled: 'normal')
        self.assertTrue(self.progress.isVisible())
        self.wait()

    def test_worker_critical_log_reports_error_without_opening_a_dialog(self):
        result = []
        self.progress.completed.connect(lambda value, error: result.append((value, error)))
        with patch('commonUtils.debugUtils.ui.display_msg_box_ok') as popup:
            self.progress.start(lambda report, cancelled: log(Severity.CRITICAL, 'Test failure', 'worker error'))
            self.wait()
        popup.assert_not_called()
        self.assertIsNone(result[0][0])
        self.assertIn('worker error', result[0][1])
        self.assertEqual(self.progress.bar.maximum(), 1000)
        self.assertEqual(self.progress.bar.value(), 0)
        self.assertIn('Operation failed', self.progress.message.text())

    def test_cancel_keeps_progress_alive_until_worker_stops(self):
        entered, release = Event(), Event()
        results = []
        def work(report, cancelled):
            entered.set()
            release.wait(5)
            return cancelled()
        self.progress.completed.connect(lambda value, error: results.append((value, error)))
        self.progress.start(work)
        try:
            self.assertTrue(entered.wait(2))
            self.progress.request_cancel()
            self.assertTrue(self.progress.busy)
            self.assertFalse(self.progress.cancel_button.isEnabled())
        finally:
            release.set()
            self.wait()
        self.assertEqual(results, [(True, '')])
        self.assertEqual(self.progress.bar.maximum(), 1000)
        self.assertEqual(self.progress.message.text(), 'Cancelled.')
