"""Compact native tab headers, cooperative closing, docking and view transfers."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import Mock, patch
from commonUtils.ui import pyside as qt
from commonUtils.ui.workspace import Workspace


class View(qt.QLabel):
    view_title = 'View'
    def __init__(self, argument):
        super().__init__('View content')
        self.state = argument
        self.closing = False
    def prepare_close(self):
        self.closing = True
        return True


class WorkspaceTests(unittest.TestCase):
    def test_drag_uses_the_full_pane_and_floating_header_tracks_the_press(self):
        workspace = self.create()
        workspace.add_view()
        dock = workspace.active_dock
        drag = Mock()
        drag.exec.return_value = qt.Qt.DropAction.MoveAction
        with patch('commonUtils.ui.workspace_drag.qt.QDrag', return_value=drag):
            workspace.drag_tab(dock)
        self.assertEqual(drag.setPixmap.call_args.args[0].size(), dock.grab().size())
        dock.setFloating(True)
        self.settle()
        event = qt.QMouseEvent(qt.QEvent.Type.MouseButtonPress, qt.QPointF(80, 10),
                              qt.QPointF(80, 10), qt.Qt.MouseButton.LeftButton,
                              qt.Qt.MouseButton.LeftButton, qt.Qt.KeyboardModifier.NoModifier)
        dock.tab_header.mousePressEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertIsNotNone(dock.tab_header._press)

    def mouse(self, widget, kind, global_point):
        button = qt.Qt.MouseButton.LeftButton
        event = qt.QMouseEvent(kind, qt.QPointF(widget.mapFromGlobal(global_point)), qt.QPointF(global_point),
            button if kind != qt.QEvent.Type.MouseMove else qt.Qt.MouseButton.NoButton,
            button if kind != qt.QEvent.Type.MouseButtonRelease else qt.Qt.MouseButton.NoButton,
            qt.Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(widget, event)
        self.settle()

    def test_horizontal_tab_drag_undocks_and_floating_header_snaps_on_both_edges(self):
        workspace = self.create()
        workspace.add_view('first'); moving = workspace.active_dock
        workspace.add_view('second'); self.settle()
        other = next(dock for dock in workspace.docks if dock is not moving)
        bar = self.tab_bar(workspace)
        index = next(i for i in range(bar.count()) if workspace._tab_dock(bar, i) is moving)
        origin = bar.mapToGlobal(bar.tabRect(index).center())
        self.mouse(bar, qt.QEvent.Type.MouseButtonPress, origin)
        self.mouse(bar, qt.QEvent.Type.MouseMove, origin + qt.QPoint(30, 0))
        self.assertTrue(moving.isFloating())
        self.assertIsNotNone(workspace._window_drag)
        outside = workspace.mapToGlobal(workspace.rect().bottomRight() + qt.QPoint(100, 100))
        self.mouse(moving.tab_header, qt.QEvent.Type.MouseButtonRelease, outside)
        self.assertTrue(moving.isFloating())
        for edge in ('left', 'right'):
            header = moving.tab_header
            origin = header.mapToGlobal(header.rect().center())
            self.mouse(header, qt.QEvent.Type.MouseButtonPress, origin)
            point = workspace.mapToGlobal(qt.QPoint(3 if edge == 'left' else workspace.width() - 3,
                                                    workspace.height() // 2))
            self.mouse(header, qt.QEvent.Type.MouseMove, point)
            self.assertTrue(workspace._drop_preview.isVisible())
            self.mouse(header, qt.QEvent.Type.MouseButtonRelease, point)
            self.assertFalse(moving.isFloating())
            self.assertNotIn(other, workspace.tabifiedDockWidgets(moving))
            self.assertEqual(moving.x() < other.x(), edge == 'left')
            self.assertEqual(moving.widget().state, 'first')

    def test_closing_a_dragged_pane_releases_the_drag_controller(self):
        workspace = self.create(); workspace.add_view('first')
        dock = workspace.active_dock
        origin = dock.tab_header.mapToGlobal(dock.tab_header.rect().center())
        workspace.begin_window_drag(dock, origin + qt.QPoint(30, 0), origin)
        dock.close(); self.settle()
        self.mouse(workspace, qt.QEvent.Type.MouseMove, origin)
        self.assertIsNone(workspace._window_drag)

    def test_browser_policy_keeps_one_attached_tab_and_closes_split_neighbors(self):
        workspace = self.create()
        workspace.keep_one_tab = True
        workspace.add_view('first'); first = workspace.active_dock
        self.settle()
        self.assertFalse(first.tab_header.close_button.isEnabled())
        self.assertTrue(first.tab_header.close_button.isHidden())
        self.assertFalse(first.close())
        self.assertFalse(first.widget().closing)
        workspace.add_view('second'); second = workspace.active_dock
        self.settle()
        bar = self.tab_bar(workspace)
        for index in range(bar.count()):
            self.assertTrue(bar.tabButton(index, qt.QTabBar.ButtonPosition.LeftSide).isEnabled())
        workspace.arrange(second, 'right', anchor=first)
        self.settle()
        first.tab_header.close_button.click(); self.settle()
        self.assertEqual(workspace.docks, [second])
        self.assertFalse(second.tab_header.close_button.isEnabled())
        self.assertTrue(second.tab_header.close_button.isHidden())
        workspace.close_action.trigger(); self.settle()
        self.assertEqual(workspace.docks, [second])
        self.assertTrue(workspace.prepare_close())
        self.assertTrue(second.close())
        self.settle()
        self.assertEqual(workspace.docks, [])

    def test_floating_tab_does_not_own_application_quit_or_replace_attached_tab(self):
        workspace = self.create(); workspace.keep_one_tab = True
        workspace.add_view('first'); first = workspace.active_dock
        workspace.add_view('floating'); floating = workspace.active_dock
        floating.setFloating(True); self.settle()
        self.assertFalse(first.tab_header.close_button.isEnabled())
        self.assertTrue(first.tab_header.close_button.isHidden())
        self.assertTrue(floating.tab_header.close_button.isEnabled())
        self.assertFalse(floating.testAttribute(qt.Qt.WidgetAttribute.WA_QuitOnClose))
        floating.tab_header.close_button.click(); self.settle()
        self.assertEqual(workspace.docks, [first])
        self.assertFalse(first.close())

    def test_drag_reveal_hook_does_not_require_an_application_page(self):
        workspace = self.create()
        workspace.add_view('first'); dock = workspace.active_dock
        workspace.add_view('second'); self.settle()
        point = workspace.mapToGlobal(workspace.rect().center())
        with patch.object(workspace, 'reveal_for_drop') as reveal:
            workspace.begin_window_drag(dock, point, point)
            reveal.assert_called_with(point)
            workspace._window_drag.finish(point, cancel=True)

    def test_retired_tab_disappears_before_worker_finishes(self):
        workspace = self.create()
        view = workspace.add_view('busy')
        dock = workspace.active_dock
        view.can_retire = True
        with patch.object(view, 'prepare_close', return_value=False):
            dock.close()
            self.assertEqual(workspace.docks, [])
            self.assertEqual(workspace._retiring, [dock])
            self.assertFalse(dock.isVisible())
            self.assertFalse(workspace.prepare_close())
        workspace._retry_view_close(dock)
        self.assertEqual(workspace._retiring, [])

    def test_dropping_tab_on_either_edge_splits_and_center_rejoins(self):
        from commonUtils.ui.workspace_drag import tab_mime
        workspace = self.create()
        workspace.add_view('first')
        moving = workspace.active_dock
        workspace.add_view('second')
        self.settle()
        for edge in ('left', 'tabs', 'right'):
            target = next(dock for dock in workspace.docks if dock is not moving)
            rect = target.geometry()
            x = rect.left() + 3 if edge == 'left' else rect.right() - 3 if edge == 'right' else rect.center().x()
            point = qt.QPoint(x, rect.center().y())
            mime = tab_mime(moving)
            enter = qt.QDragEnterEvent(point, qt.Qt.DropAction.MoveAction, mime,
                                      qt.Qt.MouseButton.LeftButton, qt.Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(workspace, enter)
            self.assertTrue(enter.isAccepted())
            drop = qt.QDropEvent(qt.QPointF(point), qt.Qt.DropAction.MoveAction, mime,
                                qt.Qt.MouseButton.LeftButton, qt.Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(workspace, drop)
            self.settle()
            self.assertTrue(drop.isAccepted())
            if edge == 'tabs':
                self.assertIn(target, workspace.tabifiedDockWidgets(moving))
            else:
                self.assertNotIn(target, workspace.tabifiedDockWidgets(moving))
                self.assertEqual(moving.x() < target.x(), edge == 'left')

    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.hosts = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for host in self.hosts:
            host.close()
            host.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def create(self):
        host = qt.QWidget()
        workspace = Workspace(View, host)
        layout = qt.QVBoxLayout(host)
        layout.addWidget(workspace)
        host.resize(900, 600)
        host.show()
        self.hosts.append(host)
        self.app.processEvents()
        return workspace

    def settle(self):
        for _ in range(5):
            self.app.processEvents()

    def tab_bar(self, workspace):
        return next(bar for bar in workspace.findChildren(qt.QTabBar)
                    if bar.parent() is workspace and bar.isVisible() and bar.count() > 1)

    def test_single_tab_uses_full_header_with_close_left_and_plus_right(self):
        workspace = self.create()
        workspace.empty_new_button.click()
        self.settle()
        dock = workspace.active_dock
        header = dock.tab_header
        self.assertEqual(workspace.findChildren(qt.QToolBar), [])
        self.assertGreater(header.width(), workspace.width() * .95)
        self.assertLess(header.close_button.x(), 5)
        self.assertGreater(header.new_button.x(), header.width() - 35)
        header.close_button.click()
        self.settle()
        self.assertEqual(workspace.docks, [])
        self.assertTrue(workspace.empty_new_button.isVisible())

    def test_tabs_share_width_after_resize_and_close_the_clicked_view(self):
        workspace = self.create()
        first = workspace.add_view('first')
        workspace.active_dock.tab_header.new_button.click()
        self.settle()
        second = workspace.active_view
        bar = self.tab_bar(workspace)
        for width in (900, 600, 1200):
            workspace.parentWidget().resize(width, 600)
            self.settle()
            widths = [bar.tabRect(index).width() for index in range(2)]
            self.assertEqual(widths[0], widths[1])
            self.assertLess(abs(sum(widths) - (bar.width() - 32)), 3)
            self.assertGreaterEqual(bar.workspace_plus.x(), bar.tabRect(1).right())
        first_index = next(index for index in range(2) if workspace._tab_dock(bar, index).widget() is first)
        button = bar.tabButton(first_index, qt.QTabBar.ButtonPosition.LeftSide)
        button.click()
        self.settle()
        self.assertEqual(len(workspace.docks), 1)
        self.assertIs(workspace.active_view, second)
        self.assertEqual(workspace.active_dock.tab_header.height(), 30)

    def test_document_tabs_share_the_entire_width_without_a_new_tab_gap(self):
        workspace = self.create()
        workspace.allow_new_tabs = False
        workspace.add_view('first'); workspace.add_view('second')
        self.settle()
        bar = self.tab_bar(workspace)
        for width in (900, 600, 1200):
            workspace.parentWidget().resize(width, 600); self.settle()
            self.assertLess(abs(sum(bar.tabRect(i).width() for i in range(2)) - bar.width()), 3)
            self.assertFalse(bar.workspace_plus.isVisible())

    def test_tab_context_menu_closes_target_and_cooperative_close_can_refuse(self):
        workspace = self.create()
        first = workspace.add_view('first')
        workspace.add_view('second')
        self.settle()
        bar = self.tab_bar(workspace)
        index = next(index for index in range(2) if workspace._tab_dock(bar, index).widget() is first)
        pos = bar.tabRect(index).center()
        event = qt.QContextMenuEvent(qt.QContextMenuEvent.Reason.Mouse, pos, bar.mapToGlobal(pos))
        actions, callbacks = [], []
        menu = Mock()
        menu.addAction.side_effect = lambda title, callback: (actions.append(title), callbacks.append(callback))
        menu.exec.side_effect = lambda position: callbacks[-1]()
        with patch('commonUtils.ui.workspace.qt.QMenu', return_value=menu), patch.object(first, 'prepare_close', return_value=False):
            self.app.sendEvent(bar, event)
        self.assertEqual(actions, ['Close tab'])
        self.assertEqual(len(workspace.docks), 2)
        with patch('commonUtils.ui.workspace.qt.QMenu', return_value=menu):
            self.app.sendEvent(bar, event)
        self.settle()
        self.assertEqual(len(workspace.docks), 1)

    def test_title_changes_and_keyboard_actions_work_without_toolbar(self):
        workspace = self.create()
        workspace.new_action.trigger()
        dock = workspace.active_dock
        dock.setWindowTitle('Renamed')
        self.assertEqual(dock.tab_header.title.text(), 'Renamed')
        workspace.new_action.trigger()
        self.settle()
        bar = self.tab_bar(workspace)
        self.assertIn('Renamed', [bar.tabText(index) for index in range(2)])
        workspace.close_action.trigger()
        self.settle()
        self.assertEqual(len(workspace.docks), 1)

    def test_plus_remains_accessible_when_tabs_overflow(self):
        workspace = self.create()
        for _ in range(16):
            workspace.add_view()
        self.settle()
        bar = self.tab_bar(workspace)
        plus = bar.workspace_plus
        for name in ('ScrollLeftButton', 'ScrollRightButton'):
            arrow = bar.findChild(qt.QToolButton, name)
            self.assertTrue(arrow.isVisible())
            self.assertFalse(plus.geometry().intersects(arrow.geometry()))
        plus.click()
        self.settle()
        self.assertEqual(len(workspace.docks), 17)

    def test_single_header_keeps_native_double_click_detaching(self):
        from PySide6.QtTest import QTest
        workspace = self.create()
        workspace.add_view()
        self.settle()
        dock = workspace.active_dock
        QTest.mouseDClick(dock.tab_header, qt.Qt.MouseButton.LeftButton,
                         pos=dock.tab_header.rect().center())
        self.settle()
        self.assertTrue(dock.isFloating())
        workspace.reattach_active()
        self.settle()
        self.assertFalse(dock.isFloating())

    def test_only_detached_view_has_large_docking_anchor_and_one_click_return(self):
        workspace = self.create()
        original = workspace.add_view({'directory': '/example', 'history': ['a', 'b']})
        dock = workspace.active_dock
        workspace.detach_active()
        self.app.processEvents()
        self.assertTrue(dock.isFloating())
        self.assertTrue(workspace._drop_target.isVisible())
        self.assertGreater(workspace._drop_target.width(), workspace.width() * .9)
        self.assertGreater(workspace._drop_target.height(), workspace.height() * .8)
        self.assertTrue(workspace.reattach_action.isEnabled())
        workspace.reattach_action.trigger()
        self.app.processEvents()
        self.assertFalse(dock.isFloating())
        self.assertFalse(workspace._drop_target.isVisible())
        self.assertFalse(workspace.reattach_action.isEnabled())
        self.assertIs(workspace.active_view, original)
        self.assertEqual(original.state['history'], ['a', 'b'])
        self.assertFalse(original.closing)
        self.assertEqual(len(workspace.docks), 1)

    def test_native_docking_into_empty_target_removes_the_anchor_after_drop(self):
        workspace = self.create()
        original = workspace.add_view('original')
        dock = workspace.active_dock
        workspace.detach_active()
        self.app.processEvents()
        # Exercise the Qt layout transition used by a tab drop onto the anchor.
        workspace.tabifyDockWidget(workspace._drop_target, dock)
        dock.setFloating(False)
        dock.show()
        dock.raise_()
        self.app.processEvents()
        self.assertFalse(workspace._drop_target.isVisible())
        self.assertFalse(dock.isFloating())
        self.assertIs(dock.widget(), original)
        self.assertEqual(len(workspace.docks), 1)
        self.assertEqual(workspace.tabifiedDockWidgets(dock), [])

    def test_top_drop_into_empty_workspace_returns_the_original_view(self):
        workspace = self.create()
        view = workspace.add_view({'history': ['a', 'b']})
        dock = workspace.active_dock
        workspace.detach_active()
        self.settle()
        top = qt.Qt.DockWidgetArea.TopDockWidgetArea
        self.assertTrue(dock.isAreaAllowed(top))
        self.assertTrue(workspace._drop_target.isAreaAllowed(top))
        # Simulate the native top-edge drop's layout transition and signals.
        workspace.addDockWidget(top, dock)
        dock.setFloating(False)
        dock.show()
        self.settle()
        self.assertFalse(dock.isFloating())
        self.assertFalse(workspace._drop_target.isVisible())
        self.assertIs(workspace.active_view, view)
        self.assertEqual(view.state['history'], ['a', 'b'])
        self.assertEqual(workspace.dockWidgetArea(dock), qt.Qt.DockWidgetArea.LeftDockWidgetArea)
        self.assertGreater(dock.width(), workspace.width() * .95)

    def test_top_drop_joins_existing_tabs_instead_of_creating_a_top_split(self):
        workspace = self.create()
        workspace.add_view('first')
        anchor = workspace.active_dock
        view = workspace.add_view('returning')
        dock = workspace.active_dock
        workspace.detach_active()
        self.settle()
        workspace.addDockWidget(qt.Qt.DockWidgetArea.TopDockWidgetArea, dock)
        dock.setFloating(False)
        dock.show()
        self.settle()
        self.assertIs(workspace.active_view, view)
        self.assertIn(dock, workspace.tabifiedDockWidgets(anchor))
        self.assertEqual(self.tab_bar(workspace).count(), 2)
        self.assertEqual(workspace.dockWidgetArea(dock), workspace.dockWidgetArea(anchor))
        self.assertFalse(view.closing)

    def test_top_tab_group_settles_without_repeated_redocking(self):
        workspace = self.create()
        workspace.add_view('first')
        first = workspace.active_dock
        workspace.add_view('second')
        second = workspace.active_dock
        workspace.addDockWidget(qt.Qt.DockWidgetArea.TopDockWidgetArea, first)
        workspace.tabifyDockWidget(first, second)
        self.settle()
        self.assertEqual(workspace.dockWidgetArea(first), qt.Qt.DockWidgetArea.LeftDockWidgetArea)
        self.assertIn(second, workspace.tabifiedDockWidgets(first))
        self.assertEqual(len(workspace.docks), 2)

    def test_new_view_stays_docked_when_previous_view_is_floating(self):
        workspace = self.create()
        workspace.add_view('original')
        floating = workspace.active_dock
        workspace.detach_active()
        self.app.processEvents()
        new = workspace.add_view('new')
        self.app.processEvents()
        self.assertTrue(floating.isFloating())
        self.assertFalse(workspace.active_dock.isFloating())
        self.assertIs(workspace.active_view, new)
        self.assertFalse(workspace._drop_target.isVisible())
        workspace.reattach_action.trigger()
        self.app.processEvents()
        self.assertFalse(floating.isFloating())
        self.assertEqual(len(workspace.docks), 2)

    def test_transfer_into_a_window_without_tabs_preserves_the_view(self):
        source = self.create()
        target = self.create()
        original = source.add_view('history')
        dock = source.active_dock
        source.detach_active()
        self.app.processEvents()
        self.assertTrue(target._drop_target.isVisible())
        target.adopt(dock)
        self.app.processEvents()
        self.assertIs(target.active_view, original)
        self.assertFalse(dock.isFloating())
        self.assertFalse(target._drop_target.isVisible())
        self.assertTrue(source._drop_target.isVisible())
        self.assertEqual(source.docks, [])
        self.assertFalse(original.closing)
