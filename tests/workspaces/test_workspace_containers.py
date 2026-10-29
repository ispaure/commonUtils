"""Container ownership, policy boundaries and reversible transfers with real Qt."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from unittest.mock import patch
from shiboken6 import isValid
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.workspaces.workspace import Workspace
from commonUtils.ui.workspaces.workspace_policy import WorkspacePolicy
from commonUtils.ui.workspaces.workspace_drag import tab_mime


class View(qt.QWidget):
    title_changed = qt.Signal(str)
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.view_title = str(state or 'Untitled')
        self.workspace_controls = qt.QHBoxLayout(self)
        self.workspace_controls.addStretch()
    def prepare_close(self):
        return True


class ContainerTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.hosts = []

    def create(self, *, browser=False, group='test'):
        policy = WorkspacePolicy(allow_last_tab_detach=not browser,
                                 show_single_tab_in_main=not browser,
                                 show_single_tab_in_detached=False,
                                 detached_title='Files: {title}' if browser else 'Documents: {title}')
        host = qt.QMainWindow()
        self.hosts.append(host)
        workspace = Workspace(View, host, policy=policy, keep_one_tab=browser, dock_group=group)
        host.setCentralWidget(workspace)
        host.resize(900, 650); host.show()
        return workspace

    def settle(self):
        for _ in range(5):
            self.app.processEvents()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def assert_owner(self, dock, owner):
        self.assertIs(dock.workspace, owner)
        self.assertIs(dock.parentWidget(), owner)
        self.assertEqual(sum(dock in workspace.docks for workspace in
                             [owner.main_workspace, *(w.workspace for w in owner.main_workspace.detached_windows)]), 1)

    def test_browser_single_tab_cannot_detach_or_move_and_header_has_no_row(self):
        source = self.create(browser=True)
        source.add_view('first'); dock = source.active_dock
        self.settle()
        self.assertEqual(dock.tab_header.height(), 0)
        self.assertEqual(dock.tab_header.sizeHint().height(), 0)
        self.assertEqual(dock.widget().y(), 0)
        self.assertTrue(dock.local_new_button.isVisible())
        self.assertIsNone(source.detach_active())
        target = self.create(browser=True)
        self.assertFalse(target.adopt(dock))
        self.assert_owner(dock, source)
        point = source.mapToGlobal(source.rect().center())
        source.begin_window_drag(dock, point, point)
        self.assertIsNone(source._window_drag)

    def test_detached_browser_plus_is_local_and_headers_adapt(self):
        main = self.create(browser=True)
        main.add_view('main'); main.add_view('floating')
        window = main.detach_active(); detached = window.workspace
        self.settle(); dock = detached.active_dock
        self.assertEqual(len(main.docks), 1)
        self.assertEqual(dock.tab_header.height(), 0)
        self.assertEqual(dock.widget().y(), 0)
        self.assertTrue(detached.can_move_tab(dock))
        self.assertTrue(dock.return_button.isVisible())
        dock.local_new_button.click(); self.settle()
        self.assertEqual(len(main.docks), 1)
        self.assertEqual(len(detached.docks), 2)
        bar = next(bar for bar in detached.findChildren(qt.QTabBar) if bar.parent() is detached and bar.count() == 2)
        self.assertTrue(bar.isVisible())
        self.assertEqual(detached.active_dock.widget().y(), 0)
        self.assertIsNot(detached.active_dock, dock)
        detached.close_active(); self.settle()
        self.assertEqual(detached.docks, [dock])
        self.assertEqual(dock.tab_header.height(), 0)
        self.assertTrue(dock.local_new_button.isVisible())
        if isValid(bar):
            self.assertEqual(bar.height(), 0)
        self.assertEqual(window.windowTitle(), 'Files: floating')
        window.close(); self.settle()
        self.assertEqual(len(main.docks), 1)
        self.assertEqual(main.active_view.state, 'main')
        self.assertEqual(main.detached_windows, [])
        self.assertFalse(isValid(window))

    def test_collapsed_headers_hide_their_buttons_and_restore_on_single_tab(self):
        main = self.create(browser=True)
        main.add_view('first')
        self.settle()
        first = main.active_dock
        self.assertEqual(first.tab_header.height(), 0)
        self.assertTrue(first.tab_header.new_button.isHidden())
        self.assertTrue(first.local_new_button.isVisible())
        main.add_view('second')
        self.settle()
        for dock in main.docks:
            self.assertEqual(dock.tab_header.height(), 0)
            self.assertTrue(dock.tab_header.new_button.isHidden())
            self.assertTrue(dock.tab_header.close_button.isHidden())
        bar = next(bar for bar in main.findChildren(qt.QTabBar) if bar.parent() is main and bar.count() == 2)
        self.assertTrue(bar.workspace_plus.isVisible())
        main.close_active()
        self.settle()
        self.assertTrue(first.tab_header.new_button.isHidden())
        self.assertTrue(first.local_new_button.isVisible())
        if isValid(bar):
            self.assertTrue(bar.workspace_plus.isHidden())

    def test_full_single_header_restores_buttons_after_group_collapses(self):
        main = self.create()
        main.add_view('first')
        self.settle()
        first = main.active_dock
        self.assertTrue(first.tab_header.new_button.isVisible())
        main.add_view('second')
        self.settle()
        self.assertTrue(first.tab_header.new_button.isHidden())
        main.close_active()
        self.settle()
        self.assertTrue(first.tab_header.new_button.isVisible())
        first.tab_header.new_button.click()
        self.settle()
        self.assertEqual(len(main.docks), 2)

    def test_native_window_drop_returns_last_browser_tab(self):
        from commonUtils.ui.workspaces.workspace_drag import NativeWindowDrag
        main = self.create(browser=True)
        main.add_view('main'); main.add_view('detached')
        window = main.detach_active(); self.settle()
        dock = window.workspace.active_dock
        point = main.mapToGlobal(main.rect().center())
        drag = NativeWindowDrag(window, window.geometry())
        window._native_drag = drag
        drag.move(point)
        drag.finish(point)
        self.assert_owner(dock, main)
        self.settle()
        self.assertFalse(isValid(window))

    def test_window_close_closes_all_local_tabs_and_preserves_other_windows(self):
        for browser in (False, True):
            with self.subTest(browser=browser):
                main = self.create(browser=browser)
                main.add_view('main'); attached = main.active_dock
                main.add_view('other window'); other = main.detach_active()
                main.add_view('closing window'); window = main.detach_active()
                window.workspace.add_view('second tab')
                views = [dock.widget() for dock in window.workspace.docks]
                with patch.object(views[0], 'prepare_close', return_value=True) as first, \
                     patch.object(views[1], 'prepare_close', return_value=True) as second:
                    self.assertTrue(window.close())
                    first.assert_called_once(); second.assert_called_once()
                self.settle()
                self.assertFalse(isValid(window))
                self.assertEqual(main.docks, [attached])
                self.assertEqual(main.detached_windows, [other])
                self.assertEqual(other.workspace.active_view.state, 'other window')

    def test_window_close_veto_keeps_tab_detached_and_can_be_retried(self):
        main = self.create(browser=True)
        main.add_view('main'); main.add_view('veto')
        window = main.detach_active(); workspace = window.workspace
        dock = workspace.active_dock
        with patch.object(dock.widget(), 'prepare_close', return_value=False):
            self.assertFalse(window.close()); self.settle()
            self.assertTrue(window.isVisible())
            self.assert_owner(dock, workspace)
            self.assertTrue(workspace.keep_one_tab)
            self.assertFalse(workspace._closing)
        self.assertTrue(window.close()); self.settle()
        self.assertFalse(isValid(window))
        self.assertEqual(len(main.docks), 1)

    def test_window_close_waits_for_retiring_worker_before_deleting_container(self):
        main = self.create(browser=True)
        main.add_view('main'); main.add_view('busy')
        window = main.detach_active(); workspace = window.workspace
        dock = workspace.active_dock; view = dock.widget(); view.can_retire = True
        with patch.object(view, 'prepare_close', return_value=False):
            self.assertFalse(window.close()); self.settle()
            self.assertEqual(workspace.docks, [])
            self.assertEqual(workspace._retiring, [dock])
            self.assertTrue(isValid(window))
            self.assertEqual(len(main.docks), 1)
        workspace._retry_view_close(dock); self.settle()
        self.assertFalse(isValid(window))
        self.assertEqual(main.detached_windows, [])

    def test_native_cancel_restores_destination_and_window_geometry(self):
        from commonUtils.ui.workspaces.workspace_drag import NativeWindowDrag
        main = self.create(); main.add_view('detached')
        window = main.detach_active(); self.settle()
        restored = []
        main.drop_reveal = lambda: lambda: restored.append(True)
        geometry = window.geometry()
        drag = NativeWindowDrag(window, geometry)
        window._native_drag = drag
        drag.move(main.mapToGlobal(main.rect().center()))
        window.move(window.pos() + qt.QPoint(60, 60))
        drag.finish(qt.QCursor.pos(), cancel=True)
        self.assertEqual(restored, [True])
        self.assertEqual(window.geometry(), geometry)
        self.assertEqual(len(window.workspace.docks), 1)

    def test_title_bar_command_returns_whole_container(self):
        main = self.create(browser=True)
        main.add_view('main'); main.add_view('detached')
        window = main.detach_active()
        window.workspace.add_view('another')
        self.assertTrue(window.dock_to_main())
        self.assertEqual(len(main.docks), 3)
        self.assertEqual(window.workspace.docks, [])

    def test_last_main_document_detaches_and_returns_through_visible_control(self):
        main = self.create(); original = main.add_view('original'); dock = main.active_dock
        self.settle(); self.assertEqual(dock.tab_header.height(), 30)
        window = main.detach_active(); self.settle()
        self.assertEqual(main.docks, [])
        self.assertTrue(main.empty_new_button.isVisible())
        self.assertEqual(dock.tab_header.height(), 0)
        self.assertTrue(dock.return_button.isVisible())
        self.assert_owner(dock, window.workspace)
        dock.return_button.click(); self.settle()
        self.assert_owner(dock, main)
        self.assertIs(dock.widget(), original)
        self.assertTrue(isValid(original))
        self.assertFalse(isValid(window))
        self.assertEqual(dock.tab_header.height(), 30)

    def test_titles_selection_and_renames_are_local_to_each_window(self):
        main = self.create()
        main.add_view('main'); main.add_view('first')
        window = main.detach_active(); detached = window.workspace
        second = detached.add_view('second'); self.settle()
        self.assertEqual(window.windowTitle(), 'Documents: second')
        second.title_changed.emit('edited *'); self.settle()
        self.assertEqual(window.windowTitle(), 'Documents: edited *')
        first = detached.docks[0]; first.raise_(); detached._activate(first); self.settle()
        self.assertEqual(window.windowTitle(), 'Documents: first')
        self.assertEqual(main.active_view.state, 'main')

    def test_cancelled_window_drag_restores_layout_and_owner(self):
        main = self.create(); main.add_view('first'); dock = main.active_dock
        main.add_view('second'); active = main.active_dock; self.settle()
        point = dock.tab_header.mapToGlobal(qt.QPoint(40, 15))
        main.begin_window_drag(dock, point + qt.QPoint(50, 50), point)
        main._window_drag.finish(point, cancel=True); self.settle()
        self.assert_owner(dock, main)
        self.assertFalse(dock.isFloating())
        self.assertIn(active, main.tabifiedDockWidgets(dock))
        self.assertIs(main.active_dock, active)
        self.assertEqual(main.detached_windows, [])

    def test_incompatible_target_and_cancelled_mime_drag_preserve_ownership(self):
        source = self.create(group='source'); source.add_view('original'); dock = source.active_dock
        target = self.create(group='other'); self.settle()
        self.assertFalse(target.adopt(dock))
        with patch('commonUtils.ui.workspaces.workspace_drag.qt.QDrag') as drag:
            drag.return_value.exec.return_value = qt.Qt.DropAction.IgnoreAction
            source.drag_tab(dock)
        self.assert_owner(dock, source)
        self.assertFalse(dock.isFloating())
        mime = tab_mime(dock)
        event = qt.QDropEvent(qt.QPointF(20,20), qt.Qt.DropAction.MoveAction, mime,
                             qt.Qt.MouseButton.LeftButton, qt.Qt.KeyboardModifier.NoModifier)
        self.assertFalse(target.handle_tab_drop(target, event))
        self.assert_owner(dock, source)

    def test_transfer_failure_rolls_back_source_and_does_not_close_content(self):
        source = self.create(); view = source.add_view('original'); dock = source.active_dock
        source.add_view('neighbor'); self.settle()
        target = self.create()
        original_add = target.addDockWidget
        def reject(area, candidate):
            if candidate is dock:
                raise RuntimeError('Rejected destination')
            return original_add(area, candidate)
        with patch.object(target, 'addDockWidget', side_effect=reject):
            self.assertFalse(target.adopt(dock))
        self.settle()
        self.assert_owner(dock, source)
        self.assertIs(dock.widget(), view)
        self.assertTrue(isValid(view))
        self.assertEqual(target.docks, [])
        self.assertEqual(len(source.docks), 2)

    def test_repeated_detach_return_leaves_no_windows_or_duplicate_tabs(self):
        main = self.create(); view = main.add_view('original'); dock = main.active_dock
        for _ in range(5):
            window = main.detach_active(); self.settle()
            self.assertIs(window.workspace.active_view, view)
            window.workspace.reattach_active(); self.settle()
            self.assert_owner(dock, main)
            self.assertEqual(main.docks, [dock])
            self.assertEqual(main.detached_windows, [])
            self.assertTrue(isValid(view))

    def test_failed_transfer_after_arrangement_preserves_order_selection_and_owner_signals(self):
        for failure in ('arrange', 'registration'):
            with self.subTest(failure=failure):
                source = self.create()
                for name in ('first', 'moving', 'last'):
                    source.add_view(name)
                dock = source.docks[1]
                target = self.create()
                target.add_view('target first')
                target.add_view('target last')
                self.settle()
                source._activate(dock)
                source_order, target_order = list(source.docks), list(target.docks)
                source_active, target_active = source.active_dock, target.active_dock
                owners = []
                dock.owner_changed.connect(owners.append)
                arrange = target.arrange

                def reject(*args, **kwargs):
                    arrange(*args, **kwargs)
                    if failure == 'registration':
                        target.docks.remove(dock)
                    else:
                        raise RuntimeError('Rejected after arrangement')

                with patch.object(target, 'arrange', side_effect=reject):
                    self.assertFalse(target.adopt(dock))
                self.settle()
                self.assertEqual(source.docks, source_order)
                self.assertEqual(target.docks, target_order)
                self.assertIs(source.active_dock, source_active)
                self.assertIs(target.active_dock, target_active)
                self.assert_owner(dock, source)
                self.assertTrue(isValid(dock.widget()))
                self.assertEqual(owners, [])
                self.assertFalse(source._transferring)
                self.assertFalse(target._transferring)

    def test_direct_mainwindow_views_keep_menus_in_detached_container(self):
        for platform in ('darwin', 'win32', 'linux'):
            with self.subTest(platform=platform), patch('commonUtils.ui.workspaces.workspace_menus.sys.platform', platform):
                host = qt.QMainWindow(); self.hosts.append(host)
                workspace = Workspace(lambda unused: qt.QMainWindow(), host, policy=WorkspacePolicy())
                host.setCentralWidget(workspace); host.show()
                view = workspace.add_view(); view.menuBar().addMenu('Tools')
                # Menus can be built after add_view; activation must still route them.
                window = workspace.detach_active(); self.settle()
                self.assertEqual([action.text() for action in window.menuBar().actions()], ['Tools'])
                window.dock_to_main(); self.settle()
                self.assertIs(workspace.active_view, view)
                if platform != 'darwin':
                    self.assertTrue(view.menuBar().isVisible())

    def test_hidden_main_workspace_does_not_replace_active_host_menus(self):
        from commonUtils.ui.workspaces.workspace_menus import sync_native_menus
        with patch('commonUtils.ui.workspaces.workspace_menus.sys.platform', 'darwin'):
            host = qt.QMainWindow(); self.hosts.append(host)
            host.menuBar().addMenu('Host')
            workspace = Workspace(lambda unused: qt.QMainWindow(), host, policy=WorkspacePolicy())
            host.setCentralWidget(workspace); host.show()
            first = workspace.add_view(); first.menuBar().addMenu('File')
            sync_native_menus(host, first)
            self.assertEqual([action.text() for action in host.menuBar().actions()], ['File'])
            workspace.hide()
            workspace.add_view()
            self.assertEqual([action.text() for action in host.menuBar().actions()], ['File'])


if __name__ == '__main__':
    unittest.main()
