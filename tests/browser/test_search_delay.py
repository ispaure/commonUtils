"""Typing must settle before expensive search callbacks execute."""
import asyncio
import time
import unittest
from commonUtils.ui.native.event_loop import DebouncedCallback


class NativeDelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_edit_restarts_quiet_period_and_keeps_last_query(self):
        calls = []
        callback = DebouncedCallback(calls.append)
        callback('n')
        await asyncio.sleep(.25)
        callback('needle')
        await asyncio.sleep(.25)
        self.assertEqual(calls, [])
        await asyncio.sleep(.2)
        self.assertEqual(calls, ['needle'])
        callback('cancelled')
        callback.cancel()
        await asyncio.sleep(.45)
        self.assertEqual(calls, ['needle'])


class QtDelayTests(unittest.TestCase):
    def test_edit_restarts_quiet_period_and_keeps_last_query(self):
        from commonUtils.ui import pyside as qt
        from PySide6.QtTest import QTest
        app = qt.QApplication.instance() or qt.QApplication([])
        field, calls = qt.QLineEdit(), []
        qt.connect_search(field, calls.append, pass_text=True)
        field.setText('n')
        QTest.qWait(250)
        field.setText('needle')
        QTest.qWait(250)
        self.assertEqual(calls, [])
        # A loaded native runner may dispatch a valid timer late. Keep the
        # quiet-period assertion above, then wait for the observable callback.
        deadline = time.monotonic() + 2
        while calls != ['needle'] and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertEqual(calls, ['needle'])
        field.deleteLater()
        app.processEvents()
