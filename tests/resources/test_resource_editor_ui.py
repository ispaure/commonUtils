"""Shared picker ownership, editor publication/conflicts and provider navigation."""
from pathlib import Path
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.resources.picker import ResourcePicker
from commonUtils.ui.resources.editor import ResourceTextWindow
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice, ResourceTextSession

TEST_STAGE = TestStage.REGRESSION


class ResourceEditorUITests(QtTestCase):
    def test_picker_and_editor_open_save_as_and_release(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            (root / 'note.txt').write_text('baseline')
            provider = LocalFiles(root)
            released = []
            picker = ResourcePicker([('Storage', lambda: (provider, lambda: released.append('picker')))], name='note.txt')
            self.wait_until(lambda: not picker.browser.operation.busy)
            picker.choose()
            self.wait_until(lambda: not picker.operation.busy)
            self.assertEqual(picker.choice.path, 'note.txt')
            self.assertEqual(released, [])
            choice = picker.choice
            editor = ResourceTextWindow(choice, ResourceTextSession.open(provider, choice.path),
                         lambda *args: ResourceChoice(provider, 'copy.txt', lambda: released.append('copy')), lambda *args: None)
            self.assertEqual(editor.windowTitle(), '🕵️ Private - note.txt — Text Editor')
            editor.editor.setPlainText('private draft')
            editor.save_as()
            self.wait_until(lambda: not editor.operation.busy)
            self.assertEqual(editor.session.path, 'copy.txt')
            self.assertEqual(editor.windowTitle(), '🕵️ Private - copy.txt — Text Editor')
            self.assertEqual((root / 'copy.txt').read_text(), 'private draft')
            self.assertEqual((root / 'note.txt').read_text(), 'baseline')
            self.assertEqual(released, ['picker'])
            editor.editor.setPlainText('retained on conflict')
            (root / 'copy.txt').write_text('external')
            editor.save()
            self.wait_until(lambda: not editor.operation.busy)
            self.assertEqual(editor.editor.toPlainText(), 'retained on conflict')
            self.assertIn('retained', editor.status.text())
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard):
                editor.close()
            self.assertEqual(released, ['picker', 'copy'])
            picker.deleteLater()

    def test_picker_storage_titles_and_breadcrumb_navigation(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            (root / 'folder').mkdir()
            local = LocalFiles(root)
            private = LocalFiles(root)
            private.private = True
            picker = ResourcePicker([('Local', lambda: (local, lambda: None)),
                                     ('Crypt', lambda: (private, lambda: None))])
            self.wait_until(lambda: not picker.browser.operation.busy)
            self.assertEqual(picker.windowTitle(), 'Open')
            picker.switch(1)
            self.wait_until(lambda: not picker.browser.operation.busy)
            self.assertEqual(picker.windowTitle(), '🕵️ Private - Open')
            browser = picker.browser
            with patch.object(qt.QFileIconProvider, 'icon', side_effect=AssertionError('Virtual path icon lookup')):
                browser.navigate(root / 'folder')
                self.wait_until(lambda: not browser.operation.busy)
            self.assertEqual(browser.breadcrumbs.paths, [root, root / 'folder'])
            browser.breadcrumbs.root_button.click()
            self.wait_until(lambda: not browser.operation.busy)
            self.assertEqual(browser.navigation.directory, root)
            browser.back.click()
            self.wait_until(lambda: not browser.operation.busy)
            self.assertEqual(browser.navigation.directory, root / 'folder')
            picker.switch(0)
            self.wait_until(lambda: not picker.browser.operation.busy)
            self.assertEqual(picker.windowTitle(), 'Open')
            picker.reject()
            picker.deleteLater()
