"""Selection preview and private status presentation, using real Qt widgets."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from commonUtils.ui.file_browser.status import format_duration, indexing_phase, IndexProgress, private_status


class BrowserPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_elapsed_and_phase_never_include_private_paths(self):
        self.assertEqual(format_duration(59.9), '59s')
        self.assertEqual(format_duration(61), '1m 01s')
        self.assertEqual(format_duration(3661), '1h 01m 01s')
        for message in ('Indexing /private/name', 'Checking indexed folder /private/name',
                        'Reusing saved branch /private/name', 'Unexpected /private/name'):
            self.assertNotIn('/private', indexing_phase(message))
        message = private_status('Checking file metadata · /private/name · 20 processed this run · 1m 01s elapsed')
        self.assertNotIn('/private', message)
        self.assertIn('20 processed this run', message)
        self.assertIn('1m 01s elapsed', message)

    def test_counters_survive_phase_changes_and_elapsed_time_advances_without_new_work(self):
        progress = IndexProgress(started_at=0)
        progress.update(990, 'Indexing /private/name', saved_entries=900)
        progress.update(20, 'Checking indexed folder /private/name')
        progress.update(0, 'Saved progressive folder totals')
        message = progress.render(3661)
        self.assertIn('900 saved entries', message)
        self.assertIn('1,010 processed this run', message)
        self.assertIn('1h 01m 01s elapsed', message)
        self.assertNotIn('/private', message)
        self.assertIn('1h 01m 02s elapsed', progress.render(3662))

    def test_preview_opens_on_selection_and_toggle_suppresses_future_selections(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            first = root / 'first.txt'; first.write_text('first')
            second = root / 'second.txt'; second.write_text('second')
            browser = FileBrowser(root, calculate_folder_sizes=False)
            browser.resize(1000, 600); browser.show()
            def wait(condition):
                deadline = monotonic() + 5
                while not condition():
                    self.assertLess(monotonic(), deadline)
                    self.app.processEvents(); sleep(.005)
                self.app.processEvents()
            try:
                wait(lambda: browser.model.index(str(first)).isValid())
                self.assertTrue(browser.preview_toggle.isChecked())
                self.assertTrue(browser.preview_panel.isHidden())
                def select(path):
                    browser.tree.selectionModel().setCurrentIndex(browser.model.index(str(path)),
                        qt.QItemSelectionModel.SelectionFlag.ClearAndSelect | qt.QItemSelectionModel.SelectionFlag.Rows)
                    wait(lambda: not browser.busy)
                select(first)
                self.assertFalse(browser.preview_panel.isHidden())
                self.assertGreaterEqual(browser.splitter.sizes()[1], 220)
                browser.preview_toggle.setChecked(False)
                select(second)
                self.assertTrue(browser.preview_panel.isHidden())
                browser.preview_toggle.setChecked(True)
                wait(lambda: not browser.busy)
                self.assertFalse(browser.preview_panel.isHidden())
                browser.tree.selectionModel().clearSelection()
                self.app.processEvents()
                self.assertTrue(browser.preview_panel.isHidden())
            finally:
                browser.stop()
                wait(lambda: not browser.busy and not browser.folder_busy and not browser.views.cover_busy)
                browser.close(); self.app.processEvents()
