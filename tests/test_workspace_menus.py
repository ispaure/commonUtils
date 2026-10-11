"""Menu context changes publish without opening a menu or stealing focus."""
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.workspace_menus import sync_native_menus


class MenuContextTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.host = qt.QMainWindow()
        self.host.workspace = type('Detached', (), {'is_detached': True})()
        self.addCleanup(self.host.deleteLater)
        self.documents = []

    def document(self, title):
        document = qt.QMainWindow(self.host)
        document._test_menu = document.menuBar().addMenu(title)
        document._test_menu.addAction('Command')
        self.documents.append(document)
        return document

    def settle(self):
        for _ in range(3):
            self.app.processEvents()

    def titles(self):
        return [action.text() for action in self.host.menuBar().actions()]

    def test_deferred_refresh_uses_latest_context_after_rapid_switches(self):
        first, second = self.document('File'), self.document('View')
        for platform in ('darwin', 'win32', 'linux'):
            with self.subTest(platform=platform), patch('commonUtils.ui.workspace_menus.sys.platform', platform):
                sync_native_menus(self.host, first)
                sync_native_menus(self.host, second)
                self.settle()
                self.assertEqual(self.titles(), ['View'])

    def test_native_display_invalidation_coalesces_context_and_focus_changes(self):
        self.host.show(); self.settle()
        first, second = self.document('File'), self.document('Edit')
        with patch('commonUtils.ui.workspace_menus.sys.platform', 'darwin'), patch.object(
                qt.QApplication, 'platformName', return_value='cocoa'), patch.object(
                qt.QApplication, 'focusWindow', return_value=self.host.windowHandle()), patch(
                'commonUtils.ui.workspace_cocoa.redraw_menu_bar') as redraw:
            sync_native_menus(self.host, first)
            sync_native_menus(self.host, second)
            self.settle()
            redraw.assert_called_once()
            sync_native_menus(self.host, second); self.settle()
            redraw.assert_called_once()
            self.app.focusWindowChanged.emit(self.host.windowHandle()); self.settle()
            self.assertEqual(redraw.call_count, 2)
            with patch.object(qt.QApplication, 'focusWindow', return_value=None):
                sync_native_menus(self.host, first); self.settle()
            self.assertEqual(redraw.call_count, 2)

    def test_activation_resolves_current_context_without_a_tab_change(self):
        first, second = self.document('File'), self.document('Edit')
        sync_native_menus(self.host, first)
        self.settle()
        self.host.workspace_menu_document = lambda: second
        self.app.sendEvent(self.host, qt.QEvent(qt.QEvent.Type.WindowActivate))
        self.settle()
        self.assertEqual(self.titles(), ['Edit'])

    def test_native_focus_return_resolves_context_without_widget_focus_change(self):
        self.host.show(); self.settle()
        first, second = self.document('File'), self.document('Edit')
        sync_native_menus(self.host, first)
        self.settle()
        self.host.workspace_menu_document = lambda: second
        focused = self.app.focusWidget()
        self.app.focusWindowChanged.emit(self.host.windowHandle())
        self.settle()
        self.assertEqual(self.titles(), ['Edit'])
        self.assertIs(self.app.focusWidget(), focused)

    def test_menus_created_after_adoption_update_without_opening_menu(self):
        document = self.document('File')
        sync_native_menus(self.host, document)
        self.settle()
        document.menuBar().addMenu('Tools').addAction('New tool')
        self.settle()
        self.assertEqual(self.titles(), ['File', 'Tools'])
        document.menuBar().removeAction(document.menuBar().actions()[0])
        self.settle()
        self.assertEqual(self.titles(), ['Tools'])

    def test_closed_source_restores_host_menus_on_pending_refresh(self):
        self.host.menuBar().addMenu('Host')
        document = self.document('File')
        sync_native_menus(self.host, document)
        document.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.settle()
        self.assertEqual(self.titles(), ['Host'])

    def test_refresh_preserves_keyboard_focus_and_original_commands(self):
        from unittest.mock import Mock
        editor = qt.QLineEdit()
        self.host.setCentralWidget(editor)
        self.host.show(); self.host.activateWindow(); editor.setFocus()
        self.settle()
        document = self.document('File')
        command = document._test_menu.actions()[0]
        callback = Mock(); command.triggered.connect(callback)
        focused = self.app.focusWidget()
        sync_native_menus(self.host, document)
        self.settle()
        self.assertIs(self.app.focusWidget(), focused)
        routed = self.host.menuBar().actions()[0].menu().actions()[0]
        self.assertIs(routed, command)
        routed.trigger(); callback.assert_called_once()

    def test_attached_host_can_publish_context_with_global_navigation_on_each_platform(self):
        self.host.workspace.is_detached = False
        self.host.workspace_publish_menus = True
        global_menu = self.host.menuBar().addMenu('Application')
        self.host.workspace_menu_actions = [global_menu.menuAction()]
        first, second = self.document('File'), self.document('View')
        for platform in ('darwin', 'win32', 'linux'):
            with self.subTest(platform=platform), patch('commonUtils.ui.workspace_menus.sys.platform', platform):
                self.host.workspace_menu_document = lambda: second
                sync_native_menus(self.host, first)
                self.assertEqual(self.titles(), ['Application', 'View'])
                self.settle()
                self.assertTrue(second.menuBar().isHidden())
                self.host.workspace_menu_document = lambda: None
                sync_native_menus(self.host, second)
                self.settle()
                self.assertEqual(self.titles(), ['Application'])


class CocoaMenuRedrawTests(QtTestCase):
    def bridge(self, visible=True):
        from unittest.mock import Mock
        from commonUtils.ui.workspace_cocoa import CocoaMenuBar
        bridge = CocoaMenuBar.__new__(CocoaMenuBar)
        bridge.menu_class = 1
        bridge.visible_selector = 2
        bridge.set_visible_selector = 3
        bridge.visible = Mock(return_value=visible)
        bridge.set_visible = Mock()
        return bridge

    def test_intentionally_hidden_bar_stays_hidden(self):
        bridge = self.bridge(False)
        bridge.redraw()
        bridge.set_visible.assert_not_called()

    def test_visibility_is_restored_synchronously_even_on_failure(self):
        from unittest.mock import call
        bridge = self.bridge()
        bridge.set_visible.side_effect = [RuntimeError('test failure'), None]
        with self.assertRaises(RuntimeError): bridge.redraw()
        self.assertEqual(bridge.set_visible.call_args_list,
                         [call(1, 3, False), call(1, 3, True)])
