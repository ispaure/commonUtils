"""Menu placement follows one preference for existing and future windows."""
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.menu_policy import install_menu_policy, native_menus_enabled
from commonUtils.ui.workspaces.workspace_menus import sync_native_menus


class MenuPolicyTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.setting = patch('commonUtils.ui.menu_policy.get_setting', return_value=True).start()
        self.addCleanup(patch.stopall)
        self.policy = install_menu_policy(self.app)
        self.windows = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for window in self.windows:
            window.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def window(self, title, parent=None):
        window = qt.QMainWindow(parent)
        window._menu = window.menuBar().addMenu(title)
        window._menu.addAction('Command')
        self.windows.append(window)
        return window

    def settle(self):
        for _ in range(5):
            self.app.processEvents()

    def test_platform_and_default(self):
        for platform, expected in [('darwin', True), ('win32', False), ('linux', False)]:
            with patch('sys.platform', platform):
                self.assertEqual(native_menus_enabled(), expected)
        self.setting.assert_called_with('Menus', 'macos_native_bool', True)

    def test_live_toggle_existing_and_future_standalone_windows(self):
        with patch('sys.platform', 'darwin'):
            window = self.window('File')
            window.show()
            for enabled in (False, True, False):
                self.setting.return_value = enabled
                self.policy.refresh(); self.settle()
                self.assertEqual(self.app.testAttribute(qt.Qt.ApplicationAttribute.AA_DontUseNativeMenuBar), not enabled)
                if self.app.platformName() == 'cocoa':
                    self.assertEqual(window.menuBar().isNativeMenuBar(), enabled)
                self.assertEqual(window.menuBar().actions()[0].text(), 'File')
            new = self.window('Edit'); new.show(); self.settle()
            self.assertFalse(new.menuBar().isNativeMenuBar())

    def test_attached_toggle_restores_host_and_source_without_duplicates(self):
        with patch('sys.platform', 'darwin'):
            host = self.window('Host')
            document = self.window('Document', host)
            host.setCentralWidget(document)
            host.show()
            for enabled in (True, False, True, False):
                self.setting.return_value = enabled
                self.policy.refresh()
                sync_native_menus(host, document); self.settle()
                self.assertEqual([a.text() for a in host.menuBar().actions()],
                                 ['Document'] if enabled else ['Host'])
                self.assertEqual(document.menuBar().isHidden(), enabled)
                self.assertFalse(document.menuBar().isNativeMenuBar())

    def test_native_publication_settles_instead_of_rebinding_forever(self):
        with patch('sys.platform', 'darwin'), patch.object(
                qt.QApplication, 'platformName', return_value='cocoa'), patch(
                'commonUtils.ui.workspaces.workspace_cocoa.redraw_menu_bar'):
            host = self.window('Host')
            document = self.window('File', host)
            host.setCentralWidget(document)
            host.show()
            sync_native_menus(host, document)
            self.settle()
            context = host._workspace_menu_context
            with patch.object(context, 'schedule', wraps=context.schedule) as schedule:
                for _ in range(50):
                    self.app.processEvents()
                schedule.assert_not_called()
            self.assertFalse(context.pending)
            self.assertFalse(self.policy.pending)

    def test_open_menu_switches_on_hover_without_another_click(self):
        from PySide6.QtTest import QTest
        self.setting.return_value = False
        self.policy.refresh()
        host = self.window('Host')
        host.workspace = type('Detached', (), {'is_detached': True})()
        document = self.window('File', host)
        menus = [document._menu, document.menuBar().addMenu('Edit'),
                 document.menuBar().addMenu('View')]
        for menu in menus[1:]:
            menu.addAction('Command')
        host.setCentralWidget(document)
        sync_native_menus(host, document)
        host.resize(500, 300)
        host.show(); host.activateWindow(); self.settle()
        bar = host.menuBar()
        self.addCleanup(lambda: [menu.close() for menu in menus])
        QTest.mouseClick(bar, qt.Qt.MouseButton.LeftButton,
                         pos=bar.actionGeometry(bar.actions()[0]).center())
        self.assertTrue(menus[0].isVisible())
        # Use the QWindow input path: the popup owns the mouse grab, so a direct
        # QWidget mouseMove would bypass Qt's popup/menubar event routing.
        for index in (1, 2, 1, 0):
            point = bar.mapTo(host, bar.actionGeometry(bar.actions()[index]).center())
            QTest.mouseMove(host.windowHandle(), point)
            self.settle()
            self.assertEqual([menu.isVisible() for menu in menus],
                             [i == index for i in range(3)])
        QTest.keyClick(menus[0], qt.Qt.Key.Key_Escape)
        self.settle()
        self.assertFalse(any(menu.isVisible() for menu in menus))

    def test_saved_setting_is_reloaded_by_timer(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from PySide6.QtTest import QTest
        from commonUtils.configuration.settings import get_setting
        with TemporaryDirectory() as temporary, patch('sys.platform', 'darwin'):
            path = Path(temporary) / 'settings.ini'
            self.setting.side_effect = lambda *args: get_setting(*args, path=path)
            path.write_text('[Menus]\nmacos_native_bool = true\n')
            self.policy.refresh()
            path.write_text('[Menus]\nmacos_native_bool = false\n')
            QTest.qWait(650)
            self.assertFalse(self.policy.native)
            path.write_text('[Menus]\nmacos_native_bool = invalid\n')
            QTest.qWait(650)
            self.assertTrue(self.policy.native)

    def test_detached_menu_stays_in_header_when_disabled(self):
        with patch('sys.platform', 'darwin'):
            host = self.window('Host')
            host.workspace = type('Detached', (), {'is_detached': True})()
            document = self.window('Document', host)
            host.setCentralWidget(document)
            host.show()
            sync_native_menus(host, document)
            self.setting.return_value = False
            self.policy.refresh(); self.settle()
            self.assertEqual([a.text() for a in host.menuBar().actions()], ['Document'])
            self.assertFalse(host.menuBar().isNativeMenuBar())
            self.assertTrue(document.menuBar().isHidden())
            self.settle()
            self.assertFalse(self.policy.pending)
            self.assertFalse(host._workspace_menu_context.pending)
