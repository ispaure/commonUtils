from time import monotonic
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.operations import ResultWorker


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
