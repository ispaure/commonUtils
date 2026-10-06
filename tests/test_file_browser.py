"""Reusable browser works with generic files and independently registered types."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from commonUtils.fileUtils import File
from commonUtils.dirUtils import Directory
from commonUtils.filesystem import BrowserPanel, BrowserDetails, BrowserAction
from commonUtils.fileTypes.registry import register_file_type, file_types
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser


class CustomFile(File):
    def browser_panels(self):
        return (BrowserPanel('example', 'Example Information',
                             lambda: BrowserDetails((('Project value', 'Test value'),))),
                BrowserPanel('hidden', 'Optional Information',
                             lambda: BrowserDetails((('Optional', 'enabled'),)), False))

    def browser_actions(self, context):
        return (BrowserAction('example.action', 'Project Action',
                              lambda ctx: ctx.invoke('example.action', ctx.selection)),)

    def browser_activate(self, context):
        context.invoke('example.action', context.selection)
        return True


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'item.project'
        self.path.write_text('example')
        (self.root / 'other.bin').write_bytes(b'abc')
        self.calls = []
        self.browser = FileBrowser(Directory(self.root), services={'example.action': self.calls.append})
        self.browser.show()
        self.addCleanup(self.cleanup)
        self.wait()

    def cleanup(self):
        self.browser.close()
        self.wait()
        self.app.processEvents()

    def wait(self):
        deadline = time.monotonic() + 5
        while (self.browser.busy or self.browser.folder_busy or self.browser.views.cover_busy) and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()
        self.assertFalse(self.browser.busy or self.browser.folder_busy)

    def select(self, path):
        index = self.browser.model.index(str(path))
        self.browser.tree.selectionModel().setCurrentIndex(index,
            qt.QItemSelectionModel.SelectionFlag.ClearAndSelect | qt.QItemSelectionModel.SelectionFlag.Rows)
        self.wait()
        return index

    def test_generic_metadata_for_unknown_types_and_default_actions(self):
        index = self.select(self.path)
        self.assertIs(type(self.browser.selected_objects()[0]), File)
        self.assertEqual(self.browser.tabs.tabText(0), 'File Information')
        text = self.browser.preview.toPlainText()
        self.assertIn('Name: item.project', text)
        self.assertIn('Extension: project', text)
        self.assertIn('Size: 7 B', text)
        self.assertIn('Modified:', text)
        self.assertNotIn('\\n', text)
        menu = self.browser.context_menu_for(index)
        self.assertEqual(len(menu.actions()), 2)
        with patch('commonUtils.ui.desktop_actions.open_default') as opened:
            menu.actions()[0].trigger()
            opened.assert_called_once_with(self.path)
        menu.deleteLater()

    def test_registered_object_panels_actions_and_late_model_resolution(self):
        index = self.select(self.path)
        before = self.browser.model.item(index)
        registration = register_file_type(CustomFile, 'project')
        self.addCleanup(file_types.unregister, registration)
        self.browser.refresh()
        self.wait()
        self.assertIsInstance(self.browser.model.item(index), CustomFile)
        self.assertIsNot(self.browser.model.item(index), before)
        self.assertEqual(self.browser.tabs.count(), 2)
        self.assertIn('Project value: Test value', self.browser.preview.toPlainText())
        self.assertIn('Path:', self.browser.tabs.widget(0).toPlainText())
        menu = self.browser.context_menu_for(index)
        next(action for action in menu.actions() if action.text() == 'Project Action').trigger()
        self.assertEqual(len(self.calls), 1)
        self.assertIsInstance(self.calls[0][0], CustomFile)
        self.browser._activate(index)
        self.assertEqual(len(self.calls), 2)
        optional = next(action for action in self.browser.panel_menu.actions() if action.text() == 'Optional Information')
        self.assertFalse(optional.isChecked())
        optional.setChecked(True)
        self.wait()
        self.assertEqual(self.browser.tabs.count(), 3)
        self.assertIn('Optional: enabled', self.browser.preview.toPlainText())
        menu.deleteLater()

    def test_folder_generic_information_counts_and_directory_objects(self):
        folder = self.root / 'nested'
        folder.mkdir()
        (folder / 'file.dat').write_bytes(b'123456')
        self.browser.refresh()
        self.wait()
        index = self.select(folder)
        self.assertIsInstance(self.browser.selected_objects()[0], Directory)
        self.assertIn('Total size: 6 B', self.browser.preview.toPlainText())
        self.assertIn('Files: 1', self.browser.preview.toPlainText())
        self.assertEqual(self.browser.model.data(index.siblingAtColumn(1)), '6 B')
        self.browser._activate(index)
        self.assertEqual(self.browser.views.root, folder)
        self.browser.navigation.up.click()
        self.assertEqual(self.browser.views.root, self.root)

    def test_specialized_panel_failure_keeps_generic_panel_and_unknown_activation(self):
        class BrokenFile(CustomFile):
            def browser_panels(self):
                def fail():
                    raise ValueError('broken project data')
                return (BrowserPanel('broken', 'Broken Information', fail),)
        registration = register_file_type(BrokenFile, 'project')
        self.addCleanup(file_types.unregister, registration)
        self.select(self.path)
        self.assertIn('Path:', self.browser.tabs.widget(0).toPlainText())
        self.assertIn('broken project data', self.browser.preview.toPlainText())
        index = self.browser.model.index(str(self.root / 'other.bin'))
        with patch('commonUtils.ui.desktop_actions.open_default') as opened:
            self.browser._activate(index)
            opened.assert_called_once_with(self.root / 'other.bin')
