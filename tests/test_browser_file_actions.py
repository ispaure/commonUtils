"""Default browser editing works across views and interoperates with file clipboards."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch
from PySide6.QtTest import QTest
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from commonUtils.ui.file_browser.file_actions import clipboard_files, set_clipboard_files
from commonUtils.filesystem import BrowserAction


class BrowserFileActionTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / 'Example.txt'; self.file.write_text('original')
        self.folder = self.root / 'Folder'; self.folder.mkdir()
        self.browser = FileBrowser(self.root, calculate_folder_sizes=False)
        self.browser.resize(1000, 700); self.browser.show(); self.browser.activateWindow()
        self.warning = patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Ok).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.cleanup)
        qt.QApplication.clipboard().clear()
        self.wait()

    def cleanup(self):
        qt.QApplication.clipboard().clear()
        self.browser.close(); self.wait(); self.app.processEvents()

    def wait(self):
        deadline = time.monotonic() + 5
        while self.browser.busy or self.browser.views.cover_busy or self.browser.file_actions.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents(); time.sleep(.005)
        self.app.processEvents()

    def index(self, path):
        return self.browser.model.index(str(path))

    def select(self, path):
        self.browser.tree.selectionModel().setCurrentIndex(self.index(path),
            qt.QItemSelectionModel.SelectionFlag.ClearAndSelect | qt.QItemSelectionModel.SelectionFlag.Rows)
        self.wait()

    def menu(self, path=None, **kwargs):
        menu = self.browser.context_menu_for(self.index(path) if path else qt.QModelIndex(), **kwargs)
        self.addCleanup(menu.deleteLater)
        return {action.text(): action for action in menu.actions() if not action.isSeparator()}

    def editor(self):
        QTest.qWait(20)
        editors = [editor for editor in self.browser.views.findChildren(qt.QLineEdit) if editor.isVisible()]
        self.assertEqual(len(editors), 1)
        return editors[0]

    def test_paste_is_on_folders_and_empty_space_and_rename_requires_single_selection(self):
        self.select(self.file)
        file_menu = self.menu(self.file)
        self.assertNotIn('Paste', file_menu)
        self.assertTrue(file_menu['Rename'].isEnabled())
        self.assertFalse(self.menu(self.folder)['Paste'].isEnabled())
        self.assertFalse(self.menu()['Paste'].isEnabled())
        set_clipboard_files([self.file])
        self.assertTrue(self.menu(self.folder)['Paste'].isEnabled())
        self.assertTrue(self.menu()['Paste'].isEnabled())
        self.browser.tree.selectionModel().select(self.index(self.folder), qt.QItemSelectionModel.SelectionFlag.Select |
                                                 qt.QItemSelectionModel.SelectionFlag.Rows)
        self.assertFalse(self.menu(self.file)['Rename'].isEnabled())

    def test_platform_keys_open_parent_and_leave_editors_alone(self):
        for platform, modifier in (('darwin', qt.Qt.KeyboardModifier.ControlModifier),
                                   ('win32', qt.Qt.KeyboardModifier.NoModifier),
                                   ('linux', qt.Qt.KeyboardModifier.NoModifier)):
            self.browser.keyboard.platform = platform
            self.browser.navigate(self.root); self.wait()
            self.select(self.folder)
            self.browser.tree.setFocus()
            QTest.keyClick(self.browser.tree, qt.Qt.Key.Key_Down if platform == 'darwin'
                           else qt.Qt.Key.Key_Return, modifier)
            self.wait()
            self.assertEqual(self.browser.navigation.directory, self.folder)
            key = qt.Qt.Key.Key_Backspace if platform == 'win32' else qt.Qt.Key.Key_Up
            up_modifier = modifier if platform != 'linux' else qt.Qt.KeyboardModifier.AltModifier
            QTest.keyClick(self.browser.tree, key, up_modifier); self.wait()
            self.assertEqual(self.browser.navigation.directory, self.root)
        self.browser.keyboard.platform = 'darwin'
        self.select(self.file); self.browser.tree.setFocus()
        QTest.keyClick(self.browser.tree, qt.Qt.Key.Key_Return)
        editor = self.editor()
        editor.setText('Renamed.txt')
        QTest.keyClick(editor, qt.Qt.Key.Key_Return); self.wait()
        self.assertTrue((self.root / 'Renamed.txt').exists())
        self.browser.open_search()
        self.browser.search_bar.setText('abc')
        QTest.keyClick(self.browser.search_bar, qt.Qt.Key.Key_Backspace)
        self.assertEqual(self.browser.search_bar.text(), 'ab')

    def test_trash_action_removes_selected_folder_only_after_confirmation(self):
        child = self.folder / 'child.txt'; child.write_text('contents')
        self.select(self.folder)
        label = 'Move to Trash / Recycle Bin…'
        with patch.object(self.browser.file_actions, '_confirm_removal', return_value=False), \
                patch.object(self.browser.file_actions, '_system_trash') as trash:
            self.menu(self.folder)[label].trigger()
            trash.assert_not_called()
        kept = self.root / '.test-trash'
        def move(path):
            path.rename(kept)
            return True
        with patch.object(self.browser.file_actions, '_confirm_removal', return_value=True), \
                patch.object(self.browser.file_actions, '_system_trash', side_effect=move):
            self.menu(self.folder)[label].trigger(); self.wait()
        self.assertFalse(self.folder.exists())
        self.assertEqual((kept / 'child.txt').read_text(), 'contents')

    def test_unavailable_trash_keeps_items_without_automatic_permanent_delete(self):
        self.select(self.file)
        with patch.object(self.browser.file_actions, '_confirm_removal', return_value=True) as confirm, \
                patch.object(self.browser.file_actions, '_system_trash', return_value=False), \
                patch.object(qt.QMessageBox, 'exec', return_value=0):
            self.menu(self.file)['Move to Trash / Recycle Bin…'].trigger(); self.wait()
        self.assertEqual(self.file.read_text(), 'original')
        self.assertEqual(confirm.call_count, 1)

    def test_delete_key_in_search_field_edits_text_instead_of_files(self):
        self.select(self.file)
        self.browser.open_search()
        self.browser.search_bar.setText('abc')
        self.browser.search_bar.setFocus(); self.app.processEvents()
        self.browser.search_bar.setCursorPosition(1)
        with patch.object(self.browser.file_actions, 'delete') as delete:
            QTest.keyClick(self.browser.search_bar, qt.Qt.Key.Key_Delete)
            self.assertEqual(self.browser.search_bar.text(), 'ac')
            delete.assert_not_called()

    def test_removal_dialog_defaults_to_cancel_and_removed_cut_items_are_pruned(self):
        from commonUtils.file_removal import removal_plan
        plan = removal_plan([self.file])
        inspected = []
        def cancel_dialog():
            dialog = self.app.activeModalWidget()
            inspected.append(dialog.informativeText())
            self.assertEqual(dialog.defaultButton().text().replace('&', ''), 'Cancel')
            dialog.defaultButton().click()
        qt.QTimer.singleShot(0, cancel_dialog)
        self.assertFalse(self.browser.file_actions._confirm_removal(plan))
        self.assertIn('network drives', inspected[0])
        self.select(self.file)
        set_clipboard_files([self.file, self.folder], move=True)
        def move(path):
            path.rename(self.root / '.test-trash-file')
            return True
        with patch.object(self.browser.file_actions, '_confirm_removal', return_value=True), \
                patch.object(self.browser.file_actions, '_system_trash', side_effect=move):
            self.menu(self.file)['Move to Trash / Recycle Bin…'].trigger(); self.wait()
        self.assertEqual(clipboard_files()[0], (self.folder,))

    def test_copy_paste_and_cut_use_whole_selection_and_clear_only_successful_cut(self):
        self.select(self.file)
        self.menu(self.file)['Copy'].trigger()
        paths, move, marker = clipboard_files()
        self.assertEqual(paths, (self.file,)); self.assertFalse(move)
        self.menu(self.folder)['Paste'].trigger(); self.wait()
        self.assertEqual((self.folder / self.file.name).read_text(), 'original')
        self.assertTrue(self.file.exists())
        self.menu(self.file)['Cut'].trigger()
        self.assertTrue(clipboard_files()[1])
        self.menu(self.folder)['Paste'].trigger(); self.wait()
        self.assertFalse(self.file.exists())
        self.assertEqual((self.folder / 'Example copy.txt').read_text(), 'original')
        self.assertEqual(clipboard_files()[0], ())

    def test_native_local_url_clipboard_pastes_to_empty_background_without_touching_selection(self):
        external = self.root / 'external'; external.mkdir()
        path = external / '日本語.txt'; path.write_text('native clipboard')
        mime = qt.QMimeData(); mime.setUrls([qt.QUrl.fromLocalFile(str(path))])
        qt.QApplication.clipboard().setMimeData(mime)
        self.select(self.file)
        self.menu()['Paste'].trigger(); self.wait()
        self.assertEqual((self.root / path.name).read_text(), 'native clipboard')
        self.assertEqual(self.file.read_text(), 'original')

    def test_cut_completion_does_not_clear_a_new_clipboard_request(self):
        from commonUtils.ui.file_browser import file_actions as module
        entered, release = Event(), Event()
        original = module.transfer_paths
        def delayed(*args, **kwargs):
            entered.set(); release.wait(5)
            return original(*args, **kwargs)
        set_clipboard_files([self.file], move=True)
        with patch.object(module, 'transfer_paths', delayed):
            self.browser.file_actions.paste(self.folder)
            deadline = time.monotonic() + 5
            while not entered.is_set():
                self.assertLess(time.monotonic(), deadline)
                self.app.processEvents(); time.sleep(.005)
            set_clipboard_files([self.folder])
            release.set(); self.wait()
        self.assertEqual(clipboard_files()[0], (self.folder,))
        self.assertFalse(clipboard_files()[1])

    def test_cut_failure_keeps_unmoved_clipboard_paths(self):
        missing = self.root / 'missing'
        set_clipboard_files([self.file, missing], move=True)
        self.browser.file_actions.paste(self.folder); self.wait()
        self.assertEqual(clipboard_files()[0], (missing,))
        self.assertTrue(clipboard_files()[1])
        self.warning.assert_called_once()
        self.assertTrue((self.folder / self.file.name).exists())

    def test_rename_from_menu_edits_basename_in_place_in_every_view(self):
        path = self.file
        for mode in (0, 1, 2):
            self.browser.view_selector.setCurrentIndex(mode); self.app.processEvents()
            self.menu(path)['Rename'].trigger()
            editor = self.editor()
            self.assertEqual(editor.selectedText(), path.stem)
            next_path = path.with_name(f'Renamed-{mode}.txt')
            QTest.keyClicks(editor, f'Renamed-{mode}')
            QTest.keyClick(editor, qt.Qt.Key.Key_Return); self.wait()
            self.assertFalse(path.exists()); self.assertEqual(next_path.read_text(), 'original')
            self.assertEqual(self.browser.selected_object.path, next_path)
            self.assertEqual(self.browser.heading.text(), next_path.name)
            path = next_path
        self.warning.assert_not_called()

    def test_f2_and_slow_second_click_rename_but_double_click_opens(self):
        self.select(self.file)
        self.browser.tree.setFocus()
        QTest.keyClick(self.browser.tree, qt.Qt.Key.Key_F2)
        editor = self.editor()
        QTest.keyClick(editor, qt.Qt.Key.Key_Escape)
        self.assertTrue(self.file.exists())
        index = self.index(self.file)
        point = self.browser.tree.visualRect(index).center()
        QTest.mouseClick(self.browser.tree.viewport(), qt.Qt.MouseButton.LeftButton, pos=point)
        QTest.qWait(self.app.doubleClickInterval() + 50)
        QTest.mouseClick(self.browser.tree.viewport(), qt.Qt.MouseButton.LeftButton, pos=point)
        QTest.qWait(self.app.doubleClickInterval() + 50)
        editor = self.editor(); QTest.keyClick(editor, qt.Qt.Key.Key_Escape)
        with patch('commonUtils.ui.desktop_actions.open_default') as opened:
            QTest.mouseDClick(self.browser.tree.viewport(), qt.Qt.MouseButton.LeftButton, pos=point)
            self.app.processEvents(); opened.assert_called_once_with(self.file)
        self.assertFalse(any(editor.isVisible() for editor in self.browser.views.findChildren(qt.QLineEdit)))

    def test_rename_invalid_and_existing_names_preserves_files(self):
        other = self.root / 'Other.txt'; other.write_text('existing')
        index = self.index(self.file)
        for name in ('../outside.txt', '', other.name):
            self.assertFalse(self.browser.model.setData(index, name))
            self.assertEqual(self.file.read_text(), 'original')
            self.assertEqual(other.read_text(), 'existing')
        self.assertEqual(self.warning.call_count, 3)
        self.assertTrue(self.browser.model.setData(index, 'EXAMPLE.txt'))
        self.assertEqual((self.root / 'EXAMPLE.txt').read_text(), 'original')

    def test_editor_copy_shortcut_copies_text_and_browser_copy_copies_files(self):
        self.select(self.file)
        self.browser.tree.setFocus()
        QTest.keySequence(self.browser.tree, qt.QKeySequence(qt.QKeySequence.StandardKey.Copy))
        self.assertEqual(clipboard_files()[0], (self.file,))
        QTest.keyClick(self.browser.tree, qt.Qt.Key.Key_F2)
        editor = self.editor()
        QTest.keySequence(editor, qt.QKeySequence(qt.QKeySequence.StandardKey.Copy))
        self.assertEqual(qt.QApplication.clipboard().text(), self.file.stem)
        self.assertEqual(clipboard_files()[0], ())
        QTest.keyClick(editor, qt.Qt.Key.Key_Escape)

    def test_menu_orders_rename_tools_and_feature_groups_consistently(self):
        def provider(item, context):
            return (BrowserAction('bulk', 'Bulk Rename…', lambda context: None, category='rename', order=10),
                    BrowserAction('zip', 'Create ZIP', lambda context: None, source='Archives', order=50),
                    BrowserAction('compress', 'Compress Comics', lambda context: None, source='Comics', order=20),
                    BrowserAction('metadata', 'Edit Metadata', lambda context: None, source='Comics', order=10))
        self.browser.action_providers = (provider,)
        self.select(self.file)
        menu = self.browser.context_menu_for(self.index(self.file)); self.addCleanup(menu.deleteLater)
        labels = [action.text() for action in menu.actions() if action.text()]
        self.assertEqual(labels[:5], ['Open in Default App', 'Cut', 'Copy', 'Rename', 'Bulk Rename…'])
        self.assertLess(labels.index('Edit Metadata'), labels.index('Compress Comics'))
        self.assertLess(labels.index('Comics'), labels.index('Archives'))
        self.assertTrue(labels[-1].startswith('Reveal in '))

    def test_close_during_transfer_waits_for_current_item_and_cancels_remaining(self):
        from commonUtils.ui.file_browser import file_actions as module
        entered, release = Event(), Event()
        original = module.transfer_paths
        def delayed(*args, **kwargs):
            entered.set(); release.wait(5)
            return original(*args, **kwargs)
        set_clipboard_files([self.file])
        with patch.object(module, 'transfer_paths', delayed):
            self.browser.file_actions.paste(self.folder)
            deadline = time.monotonic() + 5
            while not entered.is_set():
                self.assertLess(time.monotonic(), deadline)
                self.app.processEvents(); time.sleep(.005)
            self.browser.close()
            self.assertTrue(self.browser.file_actions.busy)
            self.assertTrue(self.browser.file_actions.task.cancelled.is_set())
            self.assertTrue(self.browser.isHidden())
            release.set(); self.wait()
        self.assertFalse((self.folder / self.file.name).exists())
        self.assertTrue(self.file.exists())

    def test_native_gnome_cut_clipboard_without_uri_list_and_alias_paths_moves_correctly(self):
        alias = self.root / 'Alias'; alias.symlink_to(self.root, target_is_directory=True)
        source = alias / self.file.name
        mime = qt.QMimeData()
        uri = qt.QUrl.fromLocalFile(str(source)).toString(qt.QUrl.ComponentFormattingOption.FullyEncoded)
        mime.setData('x-special/gnome-copied-files', f'cut\n{uri}'.encode())
        qt.QApplication.clipboard().setMimeData(mime)
        self.browser.file_actions.paste(self.folder); self.wait()
        self.assertFalse(self.file.exists())
        self.assertEqual((self.folder / self.file.name).read_text(), 'original')
        self.assertEqual(clipboard_files()[0], ())

    def test_empty_column_background_targets_its_folder_even_with_a_deeper_selection(self):
        self.browser.view_selector.setCurrentIndex(2)
        columns = self.browser.views.columns
        columns.selectionModel().setCurrentIndex(self.index(self.folder),
            qt.QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.wait()
        self.assertEqual(self.browser.views.browsing_directory(), self.folder)
        root_column = next(child for child in columns.findChildren(qt.QListView)
                           if child.isVisible() and child.rootIndex() == self.index(self.root))
        point = qt.QPoint(10, root_column.viewport().height() - 10)
        self.assertFalse(root_column.indexAt(point).isValid())
        requested = []
        self.browser.views.context_requested.disconnect(self.browser._context_menu)
        self.browser.views.context_requested.connect(requested.append)
        root_column.customContextMenuRequested.emit(point)
        self.assertFalse(requested[-1].isValid())
        self.assertEqual(self.browser.views.context_directory, self.root)
        set_clipboard_files([self.file])
        self.menu(directory=self.browser.views.context_directory)['Paste'].trigger(); self.wait()
        self.assertEqual((self.root / 'Example copy.txt').read_text(), 'original')
        self.assertFalse((self.folder / self.file.name).exists())

    def test_right_click_other_columns_and_copy_selected_row_operate_on_filename(self):
        date = self.index(self.file).siblingAtColumn(3)
        point = self.browser.tree.visualRect(date).center()
        QTest.mouseClick(self.browser.tree.viewport(), qt.Qt.MouseButton.LeftButton, pos=point)
        self.wait()
        self.assertEqual(tuple(item.path for item in self.browser.selected_objects()), (self.file,))
        self.browser.tree.setFocus()
        QTest.keySequence(self.browser.tree, qt.QKeySequence(qt.QKeySequence.StandardKey.Copy))
        self.assertEqual(clipboard_files()[0], (self.file,))
        menu = self.browser.context_menu_for(date); self.addCleanup(menu.deleteLater)
        next(action for action in menu.actions() if action.text() == 'Rename').trigger()
        editor = self.editor()
        self.assertEqual(editor.selectedText(), self.file.stem)
        QTest.keyClick(editor, qt.Qt.Key.Key_Escape)
        self.browser.view_selector.setCurrentIndex(1); self.app.processEvents()
        proxy = self.browser.views.covers.mapFromSource(self.index(self.file))
        menu = self.browser.context_menu_for(proxy); self.addCleanup(menu.deleteLater)
        self.assertIn('Rename', [action.text() for action in menu.actions()])

    def test_inline_unicode_basename_selection_preserves_extension_when_typing(self):
        path = self.root / '😀日本語.txt'; path.write_text('unicode')
        self.wait_for_visible_file(path)
        self.menu(path)['Rename'].trigger()
        editor = self.editor()
        self.assertEqual(editor.selectedText(), path.stem)
        editor.insert('Renamed')
        self.assertEqual(editor.text(), 'Renamed.txt')
        QTest.keyClick(editor, qt.Qt.Key.Key_Return); self.wait()
        self.assertFalse(path.exists())
        self.assertEqual((self.root / 'Renamed.txt').read_text(), 'unicode')

    def wait_for_visible_file(self, path):
        deadline = time.monotonic() + 5
        model, root = self.browser.model, self.browser.tree.rootIndex()
        while path not in {Path(model.filePath(model.index(row, 0, root))) for row in range(model.rowCount(root))}:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents(); time.sleep(.005)
        QTest.qWait(20)

    def test_open_menu_rename_keeps_its_item_when_new_files_reorder_rows(self):
        self.wait_for_visible_file(self.file)
        actions = self.menu(self.file)
        other = self.root / 'AAAA-first.txt'; other.write_text('new first row')
        self.wait_for_visible_file(other)
        actions['Rename'].trigger()
        editor = self.editor()
        self.assertEqual(editor.text(), self.file.name)
        editor.insert('Renamed')
        QTest.keyClick(editor, qt.Qt.Key.Key_Return); self.wait()
        self.assertEqual((self.root / 'Renamed.txt').read_text(), 'original')
        self.assertEqual(other.read_text(), 'new first row')
