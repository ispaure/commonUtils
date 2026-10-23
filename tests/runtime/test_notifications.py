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
