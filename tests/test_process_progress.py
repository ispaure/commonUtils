import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.process_runner import ProcessRunner, ProcessUpdate
from commonUtils.ui.process_progress import ProcessProgressWindow


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.windows = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for window in self.windows:
            window.runner.cancel()
            self.wait(window)
            window.close()
        self.app.processEvents()

    def create(self, **options):
        window = ProcessProgressWindow('Test operation', runner=ProcessRunner(**options))
        self.windows.append(window)
        window.show()
        return window

    def wait(self, window):
        deadline = time.monotonic() + 5
        while window.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()

    def test_incremental_output_progress_and_actual_exit_result(self):
        window = self.create(parser=lambda line: ProcessUpdate(1, 2, 'Half done') if line == 'first' else None)
        window.start(sys.executable, ['-u', '-c', "import time; print('first'); time.sleep(.3); print('last'); raise SystemExit(7)"])
        deadline = time.monotonic() + 3
        while 'first' not in window.log.toPlainText():
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(window.busy)
        self.assertEqual(window.bar.value(), 500)
        self.wait(window)
        self.assertEqual(window.result.state, 'failed')
        self.assertEqual(window.result.exit_code, 7)
        self.assertIn('last', window.log.toPlainText())
        self.assertTrue(window.isVisible())

    def test_retry_reports_successful_attempt_and_cancellation(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'attempt'
            code = f"from pathlib import Path; p=Path({str(path)!r}); n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); print(n); raise SystemExit(0 if n==2 else 1)"
            window = self.create(max_attempts=3, retry_delay_ms=10)
            window.start(sys.executable, ['-u', '-c', code])
            self.wait(window)
            self.assertTrue(window.result.succeeded)
            self.assertEqual(window.result.attempt, 2)
            self.assertIn('attempt 2', window.details.text())
        cancelled = self.create()
        cancelled.start(sys.executable, ['-u', '-c', 'import time; time.sleep(30)'])
        cancelled.runner.cancel()
        self.wait(cancelled)
        self.assertEqual(cancelled.result.state, 'cancelled')

    def test_failed_start_is_failed_and_can_cancel_pending_retry(self):
        window = self.create()
        window.start('/nonexistent/logistics-test-executable')
        self.wait(window)
        self.assertEqual(window.result.state, 'failed')
        retry = self.create(max_attempts=3, retry_delay_ms=1000)
        retry.start('/nonexistent/logistics-test-executable')
        deadline = time.monotonic() + 3
        while not retry.runner.retry_timer.isActive():
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.01)
        retry.runner.cancel()
        self.assertFalse(retry.busy)
        self.assertEqual(retry.result.state, 'cancelled')

    def test_known_work_can_reach_100_percent_before_real_completion(self):
        updates = {'known': ProcessUpdate(10, 10, 'Checking / discovering files…', metrics={'progress_basis': 'bytes'}),
                   'more': ProcessUpdate(10, 20, 'Transferring…', metrics={'progress_basis': 'bytes'})}
        window = ProcessProgressWindow('Transfer', context={'operation': 'Copy'},
            runner=ProcessRunner(parser=updates.get))
        self.windows.append(window); window.show()
        window.start(sys.executable, ['-u', '-c',
            "import time; print('known'); time.sleep(.4); print('more'); time.sleep(.4)"])
        def wait_for(format):
            deadline = time.monotonic() + 3
            while window.bar.format() != format:
                self.assertLess(time.monotonic(), deadline)
                self.app.processEvents(); time.sleep(.005)
        wait_for('100% of known work · Still running')
        self.assertTrue(window.busy)
        self.assertIn('Still running', window.state.text())
        self.assertIn('Scanning or final checks', window.details.text())
        self.assertNotEqual(window.bar.property('operationState'), 'succeeded')
        wait_for('Transferred: %p% of known work')
        self.assertEqual(window.bar.value(), 500)
        self.assertTrue(window.busy)
        self.wait(window)
        self.assertEqual(window.bar.format(), 'Complete')
        self.assertEqual(window.bar.property('operationState'), 'succeeded')
        self.assertIn('#247a46', window.bar.styleSheet())
