import unittest
from unittest.mock import Mock
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.workspaces.scoped_tabs import ScopedTabBar
from commonUtils.ui.workspaces.workspace import Workspace
from commonUtils.ui.workspaces.workspace_policy import WorkspacePolicy


class ScopedTabsTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def gesture_fixture(self):
        boundary = qt.QSplitter()
        groups = [qt.QTabWidget(), qt.QTabWidget()]
        move = Mock(return_value=True)
        for group in groups:
            group.setTabBar(ScopedTabBar(group, boundary, lambda: groups, move))
            group.addTab(qt.QLabel('buffer'), 'file')
            boundary.addWidget(group)
        boundary.resize(900, 400); boundary.show()
        self.app.processEvents()
        return boundary, groups, move

    def mouse(self, receiver, kind, point, buttons=None):
        release = kind == qt.QEvent.Type.MouseButtonRelease
        event = qt.QMouseEvent(kind, qt.QPointF(receiver.mapFromGlobal(point)), qt.QPointF(point),
            qt.Qt.MouseButton.NoButton if kind == qt.QEvent.Type.MouseMove else qt.Qt.MouseButton.LeftButton,
            buttons if buttons is not None else qt.Qt.MouseButton.NoButton if release else qt.Qt.MouseButton.LeftButton,
            qt.Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(receiver, event)
        self.app.processEvents()

    def test_release_delivered_to_destination_completes_source_gesture_once(self):
        boundary, groups, move = self.gesture_fixture()
        bar = groups[0].tabBar()
        start = bar.mapToGlobal(bar.tabRect(0).center())
        end = groups[1].mapToGlobal(qt.QPoint(groups[1].width()-10, 150))
        self.mouse(bar, qt.QEvent.Type.MouseButtonPress, start)
        self.mouse(bar, qt.QEvent.Type.MouseMove, end)
        self.assertTrue(bar.preview.isVisible())
        # Capture can change during a native gesture. Release must still finish
        # the originating drag, rather than fall through to the destination.
        self.mouse(groups[1].widget(0), qt.QEvent.Type.MouseButtonRelease, end)
        move.assert_called_once_with(groups[0].widget(0), groups[1], 'right', 1)
        self.assertFalse(bar.dragging)
        self.assertFalse(bar.preview.isVisible())
        self.mouse(bar, qt.QEvent.Type.MouseButtonRelease, end)
        self.assertEqual(move.call_count, 1)

    def test_preview_updates_when_drag_returns_inside_start_threshold(self):
        boundary, groups, move = self.gesture_fixture()
        bar = groups[0].tabBar()
        start = bar.mapToGlobal(bar.tabRect(0).center())
        end = groups[1].mapToGlobal(qt.QPoint(groups[1].width()-10, 150))
        self.mouse(bar, qt.QEvent.Type.MouseButtonPress, start)
        self.mouse(bar, qt.QEvent.Type.MouseMove, end)
        self.mouse(bar, qt.QEvent.Type.MouseMove, start)
        expected = bar.target(start)[-1]
        actual = qt.QRect(bar.preview.mapTo(boundary, qt.QPoint()), bar.preview.size())
        self.assertEqual(actual, expected)
        bar.cancel_drag()

    def test_moves_delivered_to_destination_and_escape_remain_confined(self):
        boundary, groups, move = self.gesture_fixture()
        bar = groups[0].tabBar()
        start = bar.mapToGlobal(bar.tabRect(0).center())
        end = groups[1].mapToGlobal(qt.QPoint(groups[1].width()-10, 150))
        self.mouse(bar, qt.QEvent.Type.MouseButtonPress, start)
        self.mouse(groups[1].widget(0), qt.QEvent.Type.MouseMove, end)
        self.assertTrue(bar.dragging)
        self.assertTrue(bar.preview.isVisible())
        self.app.sendEvent(groups[1].widget(0), qt.QKeyEvent(qt.QEvent.Type.KeyPress,
            qt.Qt.Key.Key_Escape, qt.Qt.KeyboardModifier.NoModifier))
        self.mouse(groups[1].widget(0), qt.QEvent.Type.MouseButtonRelease, end)
        move.assert_not_called()
        self.assertFalse(bar.preview.isVisible())

    def test_lost_button_and_hidden_source_cancel_without_a_move(self):
        for reason in ('button', 'hidden'):
            with self.subTest(reason=reason):
                boundary, groups, move = self.gesture_fixture()
                bar = groups[0].tabBar()
                start = bar.mapToGlobal(bar.tabRect(0).center())
                end = groups[1].mapToGlobal(qt.QPoint(groups[1].width()-10, 150))
                self.mouse(bar, qt.QEvent.Type.MouseButtonPress, start)
                self.mouse(bar, qt.QEvent.Type.MouseMove, end)
                if reason == 'button':
                    self.mouse(groups[1], qt.QEvent.Type.MouseMove, end, qt.Qt.MouseButton.NoButton)
                else:
                    groups[0].hide(); self.app.processEvents()
                self.assertFalse(bar.dragging)
                self.assertFalse(bar.preview.isVisible())
                move.assert_not_called()
                boundary.close()

    def test_plain_click_and_short_move_do_not_call_host_or_keep_observer(self):
        boundary, groups, move = self.gesture_fixture()
        bar = groups[0].tabBar()
        start = bar.mapToGlobal(bar.tabRect(0).center())
        self.mouse(bar, qt.QEvent.Type.MouseButtonPress, start)
        self.mouse(bar, qt.QEvent.Type.MouseMove, start + qt.QPoint(1, 0))
        self.assertFalse(bar.dragging)
        self.mouse(bar, qt.QEvent.Type.MouseButtonRelease, start)
        self.assertFalse(bar._observing_gesture)
        self.assertIsNone(bar.view)
        move.assert_not_called()

    def test_latest_target_wins_after_crossing_multiple_widgets(self):
        boundary, groups, move = self.gesture_fixture()
        bar = groups[0].tabBar()
        start = bar.mapToGlobal(bar.tabRect(0).center())
        right = groups[1].mapToGlobal(qt.QPoint(groups[1].width()-10, 150))
        left = groups[1].mapToGlobal(qt.QPoint(10, 150))
        self.mouse(bar, qt.QEvent.Type.MouseButtonPress, start)
        self.mouse(groups[1].widget(0), qt.QEvent.Type.MouseMove, right)
        self.mouse(groups[1], qt.QEvent.Type.MouseMove, left)
        self.mouse(groups[1].tabBar(), qt.QEvent.Type.MouseButtonRelease, left)
        move.assert_called_once_with(groups[0].widget(0), groups[1], 'left', 1)
        self.assertFalse(bar._observing_gesture)

    def test_drop_geometry_and_boundary(self):
        boundary = qt.QSplitter()
        groups = [qt.QTabWidget(), qt.QTabWidget()]
        move = Mock()
        for group in groups:
            group.setTabBar(ScopedTabBar(group, boundary, lambda: groups, move))
            group.addTab(qt.QLabel('buffer'), 'file')
            boundary.addWidget(group)
        boundary.resize(900, 400)
        boundary.show()
        self.app.processEvents()
        bar = groups[0].tabBar()
        target = groups[1]
        for x, placement in ((10, 'left'), (target.width() // 2, 'tabs'), (target.width()-10, 'right')):
            result = bar.target(target.mapToGlobal(qt.QPoint(x, 100)))
            self.assertIs(result[0], target)
            self.assertEqual(result[1], placement)
        self.assertIsNone(bar.target(boundary.mapToGlobal(qt.QPoint(-20, 100))))
        # Leaving the project never creates a floating widget or calls the host.
        bar.dragging, bar.view = True, groups[0].widget(0)
        outside = boundary.mapToGlobal(qt.QPoint(-20, 100))
        event = qt.QMouseEvent(qt.QEvent.Type.MouseButtonRelease,
            qt.QPointF(bar.mapFromGlobal(outside)), qt.QPointF(outside),
            qt.Qt.MouseButton.LeftButton, qt.Qt.MouseButton.NoButton, qt.Qt.KeyboardModifier.NoModifier)
        bar.mouseReleaseEvent(event)
        move.assert_not_called()
        self.assertFalse(groups[0].widget(0).isWindow())

    def test_hidden_single_header_without_controls_retains_new_button(self):
        workspace = Workspace(lambda _: qt.QLabel('content'), policy=WorkspacePolicy(show_single_tab_in_detached=False))
        workspace.add_view()
        workspace.show()
        window = workspace.detach_dock(workspace.active_dock)
        self.app.processEvents()
        window.workspace._refresh_tab_headers()
        dock = window.workspace.active_dock
        self.assertGreater(dock.tab_header.height(), 0)
        self.assertTrue(dock.tab_header.new_button.isVisible())
        dock.tab_header.new_button.click()
        self.assertEqual(len(window.workspace.docks), 2)
        self.assertEqual(len(workspace.docks), 0)


if __name__ == '__main__':
    unittest.main()
