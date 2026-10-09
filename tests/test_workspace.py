"""Native empty-workspace docking and detached-view return behavior."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
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
