"""Shared task progress publishes results on the GUI thread after worker shutdown."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from threading import Event
import time
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from commonUtils.runtime.diagnostics import Severity, log


class OperationProgressTests(QtTestCase):
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

    def test_save_footer_stays_one_row_in_tall_and_narrow_panels(self):
        panel = qt.QWidget()
        layout = qt.QVBoxLayout(panel)
        canvas = qt.QWidget()
        canvas.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Expanding)
        layout.addWidget(canvas)
        layout.addWidget(self.progress)
        self.addCleanup(panel.deleteLater)
        release = Event()
        message = 'Saving notebook…\n' + 'Long destination path / ' * 80
        self.progress.start(lambda report, cancelled: release.wait(5), message=message)
        try:
            panel.show()
            for width, height in ((1000, 800), (360, 600), (1200, 1200)):
                panel.resize(width, height)
                self.app.processEvents()
                self.assertEqual(panel.width(), width, 'Status must not widen the panel')
                self.assertEqual(self.progress.height(), self.progress.sizeHint().height())
                self.assertGreater(canvas.height(), height * .8)
                self.assertEqual(self.progress.message.text(), message)
                self.assertEqual(self.progress.message.toolTip(), message)
                self.assertFalse(self.progress.message.wordWrap())
                self.assertLessEqual(self.progress.bar.width(), 140)
                for control in (self.progress.message, self.progress.bar, self.progress.cancel_button):
                    self.assertLessEqual(abs(control.geometry().center().y() -
                                             self.progress.rect().center().y()), 1)
            self.progress.cancel_button.click()
            self.assertTrue(self.progress.cancelled.is_set())
            self.assertEqual(self.progress.message.text(), 'Cancelling safely…')
        finally:
            release.set()
            self.wait()

    def test_empty_exception_is_reported_as_failure_after_worker_shutdown(self):
        results = []
        def fail(report, cancelled):
            raise TimeoutError()
        self.progress.completed.connect(lambda value, error: results.append((value, error)))
        self.progress.start(fail)
        self.wait()
        self.assertEqual(results, [(None, 'TimeoutError')])
        self.assertEqual(self.progress.bar.value(), 0)
        self.assertIn('Operation failed', self.progress.message.text())

    def test_worker_admission_failure_completes_after_start_returns_and_allows_retry(self):
        results = []
        self.progress.completed.connect(lambda value, error: results.append((value, error)))
        for target in ('Operation', 'Operation.start'):
            with self.subTest(target=target):
                results.clear()
                try:
                    with patch('commonUtils.ui.tasks.operation_progress.' + target,
                               side_effect=RuntimeError('worker admission denied')):
                        self.progress.start(lambda report, cancelled: self.fail('Job must not run'),
                                            show_progress=False)
                    self.assertEqual(results, [])
                    self.assertTrue(self.progress.busy)
                    self.wait()
                    self.assertEqual(results, [(None, 'worker admission denied')])
                    self.assertFalse(self.progress.cancel_button.isEnabled())
                    self.assertIsNone(self.progress.operation)
                    self.assertTrue(self.progress.isHidden())
                    self.assertIn('Operation failed', self.progress.message.text())
                    self.progress.start(lambda report, cancelled: 'retry')
                    self.wait()
                    self.assertEqual(results[-1], ('retry', ''))
                finally:
                    # Baseline admission errors leave a non-running retained worker.
                    worker = self.progress.operation
                    if worker is None or not worker.isRunning():
                        self.progress.busy = False
                        self.progress.operation = None
                        if worker is not None:
                            worker.deleteLater()

    def test_empty_admission_exception_still_reports_failure(self):
        results = []
        self.progress.completed.connect(lambda value, error: results.append((value, error)))
        try:
            with patch('commonUtils.ui.tasks.operation_progress.Operation', side_effect=TimeoutError()):
                self.progress.start(lambda report, cancelled: None)
            self.wait()
            self.assertEqual(results, [(None, 'TimeoutError')])
            self.assertEqual(self.progress.bar.value(), 0)
        finally:
            if self.progress.operation is None:
                self.progress.busy = False

    def test_worker_critical_log_reports_error_without_opening_a_dialog(self):
        result = []
        self.progress.completed.connect(lambda value, error: result.append((value, error)))
        with patch('commonUtils.ui.display_msg_box_ok') as popup:
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
