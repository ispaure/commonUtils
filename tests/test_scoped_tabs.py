import unittest
from unittest.mock import Mock
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.scoped_tabs import ScopedTabBar
from commonUtils.ui.workspace import Workspace
from commonUtils.ui.workspace_policy import WorkspacePolicy


class ScopedTabsTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

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
