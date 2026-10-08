"""Unified declarations bind actions without service-name wiring."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import Mock, patch

from commonUtils.fileUtils import File
from commonUtils.dirUtils import Directory
from commonUtils.features import Feature, FileType, SelectionAction, FileActivation, BrowserExtension
from commonUtils.fileTypes.registry import file_types, file_from_path
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser


class ProjectFile(File):
    pass


class DeclarationTests(unittest.TestCase):
    def test_invalid_declarations_fail_without_installation(self):
        with self.assertRaises(TypeError):
            FileType(object, 'example')
        with self.assertRaises(ValueError):
            FileType(File, '../example')
        with self.assertRaises(TypeError):
            SelectionAction('edit', 'Edit', (object,), lambda ctx: None)
        action = SelectionAction('edit', 'Edit', File, lambda ctx: None)
        with self.assertRaises(ValueError):
            BrowserExtension(actions=(action, action))
        with self.assertRaises(TypeError):
            Feature(id='example', requires='other')

    def test_deferred_reference_does_not_import_during_declaration(self):
        with patch('commonUtils.features.importlib.import_module') as imported:
            Feature(id='deferred', file_types=[FileType('missing.package:FileClass', 'example')],
                    browser=BrowserExtension(actions=[SelectionAction('edit', 'Edit',
                        'missing.package:FileClass', lambda ctx: None)]))
        imported.assert_not_called()


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'comic.unified'
        self.path.write_bytes(b'data')
        self.other = self.root / 'other.bin'
        self.other.touch()
        self.calls = []
        self.feature = Feature(id='unified_test', label='Unified', file_types=[FileType(ProjectFile, 'unified')],
            browser=BrowserExtension(actions=[SelectionAction('edit', 'Edit selection',
                (ProjectFile, Directory), self.calls.append)],
                activation=[FileActivation(ProjectFile, self.calls.append)],
                folder_fields=lambda item, stats: (('Custom count', '1'),)))
        self.handles = self.feature.register_types()
        self.addCleanup(self.remove_types)
        self.browsers = []
        self.addCleanup(self.close_browsers)

    def remove_types(self):
        self.feature.set_enabled(True)
        for handle in self.handles:
            file_types.unregister(handle)

    def browser(self):
        browser = FileBrowser(self.root)
        self.browsers.append(browser)
        self.feature.install_browser(browser)
        self.wait(browser)
        return browser

    def wait(self, browser):
        self.app.processEvents()
        deadline = time.monotonic() + 5
        while browser.busy or browser.folder_busy or browser.views.cover_busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.01)

    def close_browsers(self):
        for browser in self.browsers:
            browser.close()
            self.wait(browser)
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def test_action_availability_is_evaluated_for_each_menu(self):
        available = Mock(return_value=False)
        self.feature.browser = BrowserExtension(actions=[SelectionAction(
            'edit', 'Edit selection', ProjectFile, self.calls.append, is_available=available)])
        browser = self.browser()
        index = browser.model.index(str(self.path))
        menu = browser.context_menu_for(index)
        self.assertNotIn('Edit selection', [action.text() for action in menu.actions()])
        available.return_value = True
        menu = browser.context_menu_for(index)
        self.assertIn('Edit selection', [action.text() for action in menu.actions()])
        self.assertEqual(available.call_args.args[0].paths, (self.path,))

    def test_actions_filter_selection_group_by_feature_and_have_no_services(self):
        browser = self.browser()
        for path in (self.path, self.other):
            browser.tree.selectionModel().select(browser.model.index(str(path)),
                qt.QItemSelectionModel.SelectionFlag.Select | qt.QItemSelectionModel.SelectionFlag.Rows)
        menu = browser.context_menu_for(browser.model.index(str(self.other)))
        self.assertEqual([action.text() for action in menu.actions() if action.property('source') == 'Unified'], ['Edit selection'])
        self.assertFalse(browser.services)
        next(action for action in menu.actions() if action.text() == 'Edit selection').trigger()
        self.assertEqual(self.calls[-1].paths, (self.path,))
        self.assertIs(self.calls[-1].browser, browser)
        menu.deleteLater()

    def test_activation_uses_clicked_file_and_keeps_unknown_file_fallback(self):
        browser = self.browser()
        browser._activate(browser.model.index(str(self.path)))
        self.assertEqual(self.calls[-1].path, self.path)
        self.assertIsInstance(self.calls[-1].item, ProjectFile)
        with patch('commonUtils.ui.desktop_actions.open_default') as opened:
            browser._activate(browser.model.index(str(self.other)))
        opened.assert_called_once_with(self.other)

    def test_toggle_updates_all_bindings_and_rejects_stale_action(self):
        first = self.browser()
        second = self.browser()
        binding = self.feature.install_browser(first)
        context = first.context(first.model.object_for_path(self.path))
        action = binding._actions_for(context.selection[0], context)[0]
        self.feature.set_enabled(False)
        self.assertIs(type(file_from_path(self.path)), File)
        for browser in (first, second):
            self.assertFalse(browser.activation_handlers)
            self.assertFalse(browser.action_providers)
            self.wait(browser)
        with self.assertRaisesRegex(RuntimeError, 'disabled'):
            action.run(context)
        self.feature.set_enabled(True)
        for browser in (first, second):
            self.assertTrue(browser.activation_handlers)
            self.assertIs(type(browser.model.object_for_path(self.path)), ProjectFile)
            self.wait(browser)

    def test_controller_factory_is_per_window_and_repeated_install_is_idempotent(self):
        class Controller(qt.QObject):
            idle = qt.Signal()
            def prepare_close(self):
                return False
        factory = Mock(side_effect=Controller)
        self.feature.browser = BrowserExtension(create_controller=factory)
        first = self.browser()
        second = self.browser()
        binding = self.feature.install_browser(first)
        self.assertIs(binding, self.feature.install_browser(first))
        self.assertEqual(factory.call_count, 2)
        self.assertIsNot(binding.controller, self.feature.install_browser(second).controller)
        self.assertFalse(binding.prepare_close())
        notifications = []
        binding.idle.connect(lambda: notifications.append('idle'))
        binding.controller.idle.emit()
        self.assertEqual(notifications, ['idle'])
