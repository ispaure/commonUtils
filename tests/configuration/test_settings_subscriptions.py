"""Queued GUI refresh and automatic subscription retirement."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.settings.monitor import subscribe_settings
from commonUtils.configuration.monitor import settings_monitor


class SettingsSubscriptionTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'settings.ini'

    def test_shared_timer_and_owner_destruction_remove_subscription(self):
        owner = qt.QWidget()
        first = subscribe_settings(self.path, lambda: None, owner)
        timer = self.app._commonutils_settings_timer
        second = subscribe_settings(self.path, lambda: None, owner)
        self.assertIs(self.app._commonutils_settings_timer, timer)
        self.assertIsNotNone(first.unsubscribe)
        self.assertIsNotNone(second.unsubscribe)
        owner.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        settings_monitor().poll()
        self.assertNotIn(self.path.resolve(), settings_monitor()._stamps)

    def test_worker_notification_is_delivered_on_gui_thread(self):
        owner = qt.QWidget()
        calls = []
        subscription = subscribe_settings(self.path, lambda: calls.append(qt.QThread.currentThread()), owner)
        thread = Thread(target=lambda: settings_monitor().notify((self.path,)))
        thread.start(); thread.join()
        self.assertEqual(calls, [])
        self.app.processEvents()
        self.assertEqual(calls, [self.app.thread()])
        subscription.stop()
        settings_monitor().notify((self.path,))
        self.app.processEvents()
        self.assertEqual(len(calls), 1)
