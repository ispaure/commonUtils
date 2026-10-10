"""Selection preview and private status presentation, using real Qt widgets."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from commonUtils.ui.file_browser.status import format_duration, indexing_phase, IndexProgress, private_status


class BrowserPresentationTests(QtTestCase):
    def test_toolbar_stays_inline_and_split_panes_cannot_shrink_into_overlap(self):
        from commonUtils.ui.workspace import Workspace
        host = qt.QWidget()
        workspace = Workspace(lambda path: FileBrowser(calculate_folder_sizes=False), host)
        layout = qt.QVBoxLayout(host)
        layout.addWidget(workspace)
        host.resize(1600, 600)
        first = workspace.add_view()
        second = workspace.add_view()
        workspace.arrange(workspace.active_dock, 'right')
        host.show()
        try:
            host.resize(300, 300)
            for _ in range(10): self.app.processEvents()
            for browser in (first, second):
                widgets = [browser.navigation, browser.search_button, browser.folder_size_button, browser.view_selector,
                           browser.preview_toggle, browser.view_selector.storage_controls]
                rects = [qt.QRect(widget.mapTo(browser, qt.QPoint()), widget.size()) for widget in widgets]
                for left, right in zip(rects, rects[1:]):
                    self.assertLess(left.right(), right.left())
                    self.assertLess(abs(left.center().y() - right.center().y()), 3)
                self.assertGreaterEqual(browser.width(), browser.minimumSizeHint().width())
        finally:
            host.close(); host.deleteLater(); self.app.processEvents()

    def test_narrow_breadcrumbs_keep_current_folder_visible_after_resize(self):
        from commonUtils.ui.file_browser.navigation import BreadcrumbBar
        bar = BreadcrumbBar()
        bar.set_paths([Path('/root with a very long name'), Path('/root/ancestor with a very long name'),
                       Path('/root/ancestor/current')])
        bar.resize(500, 40); bar.show()
        try:
            for width in (160, 300, 120):
                bar.resize(width, 40)
                for _ in range(5): self.app.processEvents()
                scroll = bar.scroll.horizontalScrollBar()
                self.assertEqual(scroll.value(), scroll.maximum())
                current = bar.buttons[-1]
                rect = qt.QRect(current.mapTo(bar.scroll.viewport(), qt.QPoint()), current.size())
                self.assertTrue(bar.scroll.viewport().rect().intersects(rect))
        finally:
            bar.close(); bar.deleteLater(); self.app.processEvents()

    def test_index_status_uses_saved_aggregates_without_counting_all_entries(self):
        from types import SimpleNamespace
        from commonUtils.ui.file_browser.index_worker import _IndexJob
        app = qt.QApplication.instance() or qt.QApplication([])
        root = Path('/fixture')
        snapshot = SimpleNamespace(
            folder_stats=lambda *args, **kw: {root: SimpleNamespace(files=100000, folders=400)},
            errors=(), children=lambda *a, **kw: (),
        )
        job = _IndexJob(root, lambda *a, **kw: None, app)
        try:
            with patch('commonUtils.ui.file_browser.index_worker.directory_cache.peek', return_value=snapshot):
                job._cached(force=True)
            self.assertEqual(job.saved_entries, 100400)
            self.assertIn('Waiting for index writer', job.last_progress)
        finally:
            job.deleteLater()

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

    def test_columns_force_file_preview_and_other_views_restore_toggle_and_folder_details(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'sub'; folder.mkdir()
            file = root / 'file.txt'; file.write_text('text')
            browser = FileBrowser(root, calculate_folder_sizes=False)
            browser.resize(1000, 600); browser.show()
            def wait(condition):
                deadline = monotonic() + 5
                while not condition():
                    self.assertLess(monotonic(), deadline)
                    self.app.processEvents(); sleep(.005)
                self.app.processEvents()
            try:
                wait(lambda: browser.model.index(str(file)).isValid() and not browser.busy)
                browser.preview_toggle.setChecked(False)
                browser.view_selector.setCurrentIndex(2)
                browser.views.select_source(browser.model.index(str(file)))
                wait(lambda: not browser.busy)
                self.assertFalse(browser.preview_panel.isHidden())
                self.assertTrue(browser.preview_toggle.isHidden())
                self.assertEqual(browser.preview_panel.parentWidget(), browser.views.columns.preview_container)
                self.assertEqual(browser.views.columns.preview_host.width(), browser.views.columns.columnWidths()[0])
                browser.views.columns.setColumnWidths([310, 240, 240, 240])
                wait(lambda: browser.views.columns.preview_host.width() == 310)
                self.assertEqual(browser.views.columns.preview_host.width(), 310)
                browser.views.select_source(browser.model.index(str(folder)))
                wait(lambda: not browser.busy)
                self.assertTrue(browser.preview_panel.isHidden())
                browser.view_selector.setCurrentIndex(0)
                wait(lambda: not browser.busy)
                self.assertFalse(browser.preview_toggle.isHidden())
                self.assertTrue(browser.preview_panel.isHidden())
                browser.preview_toggle.setChecked(True)
                wait(lambda: not browser.busy)
                browser.tree.clearSelection()
                wait(lambda: not browser.busy)
                self.assertFalse(browser.preview_panel.isHidden())
                self.assertEqual(browser.selected_object.path, browser.navigation.directory)
                self.assertEqual(browser.preview_panel.parentWidget(), browser.splitter)
                browser.view_selector.setCurrentIndex(1)
                wait(lambda: not browser.busy)
                self.assertFalse(browser.preview_panel.isHidden())
            finally:
                browser.shutdown(); browser.close(); self.app.processEvents()

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
        self.assertTrue(message.startswith('File index · 900 saved entries'))
        self.assertTrue(message.endswith(' · Saving folder sizes'))
        progress.update(0, 'Loading saved sizes')
        loading = progress.render(3661)
        self.assertEqual(message.rsplit(' · ', 1)[0], loading.rsplit(' · ', 1)[0])

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
                wait(lambda: not browser.busy)
                self.assertFalse(browser.preview_panel.isHidden())
                self.assertEqual(browser.selected_object.path, root)
                def select(path):
                    browser.tree.selectionModel().setCurrentIndex(browser.model.index(str(path)),
                        qt.QItemSelectionModel.SelectionFlag.ClearAndSelect | qt.QItemSelectionModel.SelectionFlag.Rows)
                    wait(lambda: not browser.busy)
                select(first)
                self.assertFalse(browser.preview_panel.isHidden())
                self.assertGreaterEqual(browser.splitter.sizes()[1], 220)
                browser.preview_toggle.setChecked(False)
                with patch.object(browser, 'load', wraps=browser.load) as load:
                    select(second)
                    load.assert_not_called()
                self.assertEqual(browser.selected_object.path, second)
                self.assertTrue(browser.preview_panel.isHidden())
                browser.preview_toggle.setChecked(True)
                wait(lambda: not browser.busy)
                self.assertFalse(browser.preview_panel.isHidden())
                browser.cover_pixmap = qt.QPixmap(300, 600)
                browser.cover_pixmap.fill(qt.Qt.GlobalColor.red)
                browser._scale_cover()
                browser.splitter.setSizes([780, 220])
                self.app.processEvents()
                cover = browser.cover.pixmap()
                self.assertLessEqual(cover.width() / cover.devicePixelRatio(), browser.cover.contentsRect().width())
                self.assertAlmostEqual(cover.width() / cover.height(), .5, places=2)
                browser.tree.selectionModel().clearSelection()
                wait(lambda: not browser.busy)
                self.assertFalse(browser.preview_panel.isHidden())
                self.assertEqual(browser.selected_object.path, root)
                browser.load(browser.model.object_for_path(first))
                wait(lambda: not browser.busy)
                self.assertFalse(browser.preview_panel.isHidden())
                self.assertEqual(browser.selected_object.path, first)
            finally:
                browser.stop()
                wait(lambda: not browser.busy and not browser.folder_busy and not browser.views.cover_busy)
                browser.close(); self.app.processEvents()
