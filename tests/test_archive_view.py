"""The shared archive view emits requests, independently of application policy."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.archive_view import ArchiveContents
from commonUtils.archives import Entry


class ArchiveViewTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.view = ArchiveContents()
        self.view.resize(1000, 600)
        self.view.show()
        self.addCleanup(self.view.deleteLater)
        self.view.set_entries(Path('/example/archive.zip'), (
            Entry('notes.txt', 100, 10, False, '2026-10-10 12:00'),
            Entry('small.txt', 2, 1, False, '2026-10-10 12:00'),
            Entry('folder/nested.txt', 4, 3, False, '2026-10-10 12:00'),
        ))

    def test_implicit_folders_search_and_numeric_size_sorting(self):
        self.assertIn('folder/', self.view._folder_nodes)
        self.view.files.sortItems(1, qt.Qt.SortOrder.AscendingOrder)
        names = [self.view.files.topLevelItem(i).text(0) for i in range(self.view.files.topLevelItemCount())]
        self.assertEqual(names, ['folder', 'small.txt', 'notes.txt'])
        self.view.search.setText('nested')
        self.assertEqual(self.view.files.topLevelItemCount(), 1)
        self.assertEqual(self.view.files.topLevelItem(0).text(0), 'folder/nested.txt')

    def test_preview_emits_a_request_without_reading_the_filesystem(self):
        names = []
        self.view.preview_requested.connect(names.append)
        self.view.search.setText('notes')
        item = self.view.files.topLevelItem(0)
        item.setSelected(True)
        self.view.preview_button.click()
        self.assertEqual(names, ['notes.txt'])
        self.view.show_preview('A decoded preview from the owner')
        self.assertEqual(self.view.preview_text.toPlainText(), 'A decoded preview from the owner')

    def test_context_menu_respects_owner_edit_policy_and_emits_selection(self):
        requested = []
        self.view.remove_requested.connect(requested.append)
        self.view.search.setText('notes')
        self.view.files.topLevelItem(0).setSelected(True)
        menu = self.view.context_menu()
        self.addCleanup(menu.deleteLater)
        self.assertNotIn('Remove from ZIP…', [action.text() for action in menu.actions()])
        self.view.set_state(editable=True)
        menu = self.view.context_menu()
        self.addCleanup(menu.deleteLater)
        next(action for action in menu.actions() if action.text() == 'Remove from ZIP…').trigger()
        self.assertEqual(requested, [['notes.txt']])

    def test_new_entries_reset_search_selection_and_preview(self):
        self.view.search.setText('notes')
        self.view.files.topLevelItem(0).setSelected(True)
        self.view.show_preview('Old contents')
        self.view.set_entries(Path('/other/archive.tar'), ())
        self.assertEqual(self.view.search.text(), '')
        self.assertEqual(self.view.selected_paths(), [])
        self.assertEqual(self.view.preview_text.toPlainText(), '')
        self.assertFalse(self.view.preview_button.isEnabled())
