"""Notifications keep bounded deduplicated history and support acknowledgement."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------


from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.notifications import Notice, NotificationCenter, Toast


class NoticeTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_deduplication_bounded_history_and_explicit_acknowledgement(self):
        center = NotificationCenter(limit=2)
        toast = Toast(center)
        calls = []
        first = Notice('one', 'test', '<title>', '<message>', 'cancelled', lambda: calls.append(True))
        self.assertTrue(center.publish(first))
        self.assertFalse(center.publish(first))
        self.assertEqual(toast.label.textFormat(), qt.Qt.TextFormat.PlainText)
        toast.open_details()
        self.assertEqual(calls, [True])
        self.assertNotIn('one', center.unread)
        center.publish(Notice('two', 'test', 'Done', ''))
        center.publish(Notice('three', 'test', 'Done', ''))
        self.assertEqual(list(center.records), ['two', 'three'])
        self.assertEqual(center.unread, {'two', 'three'})


    def test_completion_is_one_shot_per_run_even_after_an_ineligible_event(self):
        from commonUtils.runtime.notifications import Completion, Notice as PortableNotice

        now = 0
        short = Completion(30, clock=lambda: now)
        long = Completion(30, clock=lambda: now)
        concurrent = Completion(30, clock=lambda: now)
        observed = Completion(30, clock=lambda: now)
        cancelled = Completion(30, clock=lambda: now)
        args = ('fixture', 'Transfer complete', 'Open Transfers for details.')
        now = 29.99
        self.assertIsNone(short.finish(*args, outcome='success'))
        now = 30
        self.assertIsNone(short.finish(*args, outcome='success'))
        first = long.finish(*args, outcome='success')
        second = concurrent.finish(*args, outcome='failure')
        self.assertIsInstance(first, PortableNotice)
        self.assertNotEqual(first.id, second.id)
        self.assertIsNone(long.finish(*args, outcome='failure'))
        self.assertIsNone(observed.finish(*args, outcome='success', observed=True))
        self.assertIsNone(cancelled.finish(*args, outcome='cancelled'))

    def test_queued_toasts_keep_the_actions_of_concurrent_results(self):
        center = NotificationCenter()
        toast = Toast(center, queue=True)
        calls = []
        for identifier in ('first', 'second'):
            center.publish(Notice(identifier, 'test', identifier, 'Details',
                                  activate=lambda value=identifier: calls.append(value)))
        self.assertEqual(toast.notice.id, 'first')
        toast.open_details()
        self.assertEqual(toast.notice.id, 'second')
        toast.open_details()
        self.assertEqual(calls, ['first', 'second'])
        self.assertFalse(center.unread)
