"""Shared views accept opaque JSON identities and providers without disk access."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from io import BytesIO
from pathlib import Path
from threading import Event
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.runtime.browsing import BrowseEntry, BrowseColumn, BrowseRole
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.entry_model import EntryModel, ProviderEntryModel
from commonUtils.ui.file_browser.model import BrowserTree, ByteSortModel, _BrowserSelection
from commonUtils.ui.file_browser.views import BrowserViews
from commonUtils.ui.resources.browser import ResourceBrowser
from commonUtils.ui.resources.picker import ResourcePicker


def picture():
    image = qt.QImage(32, 20, qt.QImage.Format.Format_ARGB32)
    image.fill(qt.QColor('orange'))
    buffer = qt.QBuffer()
    buffer.open(qt.QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    return bytes(buffer.data())


class MemoryProvider:
    root = Path('/virtual/collection').absolute()
    def __init__(self):
        self.reads = []
        self.data = picture()

    def relative(self, path):
        path = Path(path)
        value = path.relative_to(self.root).as_posix() if path.is_absolute() else path.as_posix()
        return '' if value == '.' else value

    def list(self, path='', *, cancelled=lambda: False):
        self.reads.append((path, qt.QThread.currentThread()))
        rows = [('folder', True), ('image.png', False), ('note.txt', False)] if not path else [('nested.txt', False)]
        return [dict(name=name, path='/'.join(p for p in (path, name) if p), directory=directory, size=100, modified='2026-10-13') for name, directory in rows]

    def entry(self, path):
        return dict(path=self.relative(path), name=Path(path).name, directory=False, revision=1, size=100, modified='2026-10-13')

    def open(self, path):
        return BytesIO(self.data)


class EntryBrowserTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_provider_columns_and_readable_local_modified_dates(self):
        from datetime import datetime
        from commonUtils.filesystem import format_datetime
        provider = MemoryProvider()
        model = ProviderEntryModel(provider)
        self.assertEqual([model.headerData(i, qt.Qt.Orientation.Horizontal) for i in range(3)],
                         ['Name', 'Date Modified', 'Size'])
        for stamp, expected in (
                ('2026-02-11T18:45:00', 'Feb 11, 2026 at 6:45 PM'),
                ('2026-02-11T23:45:00.123456789Z',
                 format_datetime(datetime.fromisoformat('2026-02-11T23:45:00+00:00').astimezone())),
                ('2026-02-11T18:45:00-05:00',
                 format_datetime(datetime.fromisoformat('2026-02-11T18:45:00-05:00').astimezone())),
                ('', '—'), ('invalid', '—')):
            with self.subTest(stamp=stamp):
                model.set_children(provider.root, model.entries([
                    dict(name='note.txt', path='note.txt', directory=False, size=100, modified=stamp)]))
                index = model.browse_index(provider.root / 'note.txt', 1)
                self.assertEqual(index.data(), expected)
                self.assertEqual(index.data(BrowseRole.SortValue), stamp)
                size = index.siblingAtColumn(2)
                self.assertEqual(size.data(), '100 B')
                self.assertEqual(size.data(BrowseRole.SortValue), 100)

    def test_recursive_search_opens_nested_results_and_close_restores_folder(self):
        class Provider(MemoryProvider):
            def list(self, path='', *, cancelled=lambda: False):
                if path:
                    return [dict(name='nested-note.txt', path=path + '/nested-note.txt', directory=False, size=7, modified='')]
                return super().list(path, cancelled=cancelled)
        provider = Provider()
        browser = ResourceBrowser(provider, preview=False)
        browser.show()
        self.wait_until(lambda: not browser.busy)
        browser.open_search()
        browser.filter.setText('nested')
        self.wait_until(lambda: not browser.busy)
        self.assertEqual(browser.tree.topLevelItemCount(), 1)
        rows = browser.model.tree.entries
        identity = provider.root / 'folder/nested-note.txt'
        self.assertIn(identity, rows)
        opened = []
        browser.activated.connect(opened.append)
        browser._activate(browser.model.browse_index(identity))
        self.assertEqual(opened, [identity])
        browser.close_search()
        self.assertEqual(browser.tree.topLevelItemCount(), 3)
        browser.stop()
        self.wait_until(lambda: not browser.busy)
        browser.close()

    def test_provider_search_uses_regular_chrome_and_restores_unfiltered_view(self):
        browser = ResourceBrowser(MemoryProvider(), preview=False)
        browser.resize(800, 500)
        browser.show()
        self.wait_until(lambda: not browser.busy)
        self.assertTrue(browser.search_panel.isHidden())
        self.assertIs(browser.search_panel.parentWidget(), browser.files_panel)
        browser.open_search()
        self.assertTrue(browser.search_button.isChecked())
        self.assertFalse(browser.search_panel.isHidden())
        self.assertTrue(browser.clear_search.isEnabled())
        browser.search_bar.setText('note')
        self.wait_until(lambda: not browser.busy)
        self.assertEqual(browser.tree.topLevelItemCount(), 1)
        browser.close_search_button.click()
        self.assertEqual(browser.filter.text(), '')
        self.assertTrue(browser.search_panel.isHidden())
        self.assertFalse(browser.clear_search.isEnabled())
        self.assertFalse(hasattr(browser, 'index_search'))
        self.assertEqual(browser.tree.topLevelItemCount(), 3)
        browser.stop()
        self.wait_until(lambda: not browser.busy)
        browser.close()

    def test_provider_preview_shares_sidebar_and_column_panel_without_disk_access(self):
        from commonUtils.filesystem import BrowserDetails
        provider = MemoryProvider()
        threads = []
        def metadata(row, cancelled):
            threads.append(qt.QThread.currentThread())
            return [('Metadata', BrowserDetails((('Title', 'Private title'),), picture()))]
        with patch.object(Path, 'stat', side_effect=AssertionError('Provider preview queried disk')):
            browser = ResourceBrowser(provider, details=metadata)
            self.addCleanup(browser.deleteLater)
            browser.resize(1100, 600)
            browser.show()
            self.wait_until(lambda: not browser.busy)
            for mode in (0, 1, 2):
                browser.views.set_mode(mode)
                browser.views.select_source(browser.model.browse_index(provider.root / 'image.png'))
                self.wait_until(lambda: browser.tabs.count() == 2 and not browser.busy)
                self.assertTrue(browser.preview_panel.isVisible())
                self.assertIn('Size:', browser.tabs.widget(0).toPlainText())
                self.assertIn('Private title', browser.tabs.widget(1).toPlainText())
                if mode == 2:
                    self.assertTrue(browser.views.columns.preview_container.isAncestorOf(browser.preview_panel))
                else:
                    self.assertIs(browser.preview_panel.parentWidget(), browser.splitter)
            self.assertTrue(all(thread != self.app.thread() for thread in threads))
            browser.stop()
            self.wait_until(lambda: not browser.busy)
            browser.close()

    def test_thumbnail_workers_run_together_and_stop_waits_for_both(self):
        from threading import Lock
        provider = MemoryProvider()
        release, lock, started = Event(), Lock(), []
        self.addCleanup(release.set)
        def thumbnail(path, size, cancelled):
            with lock:
                started.append(path)
            release.wait(5)
            return provider.data
        browser = ResourceBrowser(provider, thumbnail=thumbnail, preview=False)
        self.addCleanup(browser.deleteLater)
        browser.resize(900, 500)
        browser.show()
        self.wait_until(lambda: not browser.operation.busy)
        browser.views.set_mode(1)
        self.wait_until(lambda: len(started) == 2)
        self.assertEqual(len(browser.views.cover_jobs), 2)
        self.assertTrue(browser.stop())
        self.assertTrue(browser.busy)
        release.set()
        self.wait_until(lambda: not browser.busy)
        self.assertFalse(browser.views.covers.icons)
        browser.close()

    def test_revisioned_thumbnails_survive_unchanged_snapshots_and_expire_on_change(self):
        from commonUtils.ui.file_browser.thumbnails import CoverModel
        model = EntryModel(BrowseEntry('root', 'Root', True))
        entry = BrowseEntry('image', 'Image', revision=1, thumbnail=lambda size, cancelled: picture())
        model.set_children('root', [entry])
        covers = CoverModel(model)
        self.addCleanup(covers.deleteLater)
        self.addCleanup(model.deleteLater)
        covers.complete('image', picture())
        epoch = covers.epoch
        model.set_children('root', [entry, BrowseEntry('other', 'Other')])
        self.assertIn('image', covers.icons)
        self.assertGreater(covers.epoch, epoch)
        model.set_children('root', [BrowseEntry('image', 'Image', revision=2, thumbnail=entry.thumbnail)])
        self.assertNotIn('image', covers.icons)
        covers.complete('image', picture())
        model.set_children('root', [])
        self.assertNotIn('image', covers.icons)

    def test_json_identities_custom_columns_and_all_three_views_without_stat(self):
        root, folder, species = ('taxonomy', 0), 42, ('species', 'lion')
        with patch.object(Path, 'stat', side_effect=AssertionError('A JSON view queried disk')):
            model = EntryModel(BrowseEntry(root, 'Animal kingdom', True),
                [BrowseColumn('name', 'Species'), BrowseColumn('habitat', 'Habitat')])
            model.set_children(root, [BrowseEntry(folder, 'Mammals', True)])
            model.set_children(folder, [BrowseEntry(species, 'Lion', properties={'habitat': 'Savanna'},
                thumbnail=lambda size, cancelled: picture(), badge='Protected')])
            tree = BrowserTree()
            sort = ByteSortModel(model)
            tree.setModel(sort)
            tree.setSelectionModel(_BrowserSelection(sort, tree))
            views = BrowserViews(model, tree)
            self.addCleanup(views.deleteLater)
            views.navigation_root = root
            views.resize(800, 500)
            views.set_root(folder)
            views.show()
            for mode in (0, 1, 2, 0):
                views.set_mode(mode)
                views.select_source(model.browse_index(species))
                self.app.processEvents()
                self.assertEqual([index.data(BrowseRole.Identity) for index in views.selected_rows()], [species])
                self.assertEqual(views.browsing_directory(), folder)
            self.assertEqual(model.headerData(1, qt.Qt.Orientation.Horizontal), 'Habitat')
            self.assertEqual(model.browse_index(species, 1).data(), 'Savanna')
            self.assertIsNone(views.storage)
            views.set_mode(1)
            self.wait_until(lambda: species in views.covers.icons)
            self.assertTrue(all(isinstance(identity, tuple) for identity in views.covers.icons))
            views.stop()
            self.wait_until(lambda: not views.cover_busy)
            self.assertEqual(len(views.covers.icons), 0)
            views.close()

    def test_provider_columns_load_children_on_worker_and_tiles_use_memory_thumbnail(self):
        provider = MemoryProvider()
        with patch.object(Path, 'stat', side_effect=AssertionError('Virtual browsing queried disk')):
            browser = ResourceBrowser(provider)
            self.addCleanup(browser.deleteLater)
            browser.resize(850, 500)
            browser.show()
            self.wait_until(lambda: not browser.busy)
            self.assertEqual(browser.tree.topLevelItemCount(), 3)
            browser.view_selector.setCurrentIndex(2)
            browser.views.select_source(browser.model.browse_index(provider.root / 'folder'))
            self.wait_until(lambda: provider.root / 'folder' in browser.model.tree.children and not browser.busy)
            self.assertEqual(browser.navigation.directory, provider.root / 'folder')
            self.wait_until(lambda: any(column.isVisible() and column.rootIndex().data(BrowseRole.Identity) == provider.root / 'folder'
                                and column.model().rowCount(column.rootIndex()) == 1
                                for column in browser.views.columns.findChildren(qt.QListView)))
            self.assertTrue(all(thread != self.app.thread() for _, thread in provider.reads))
            browser.up.click()
            self.wait_until(lambda: not browser.busy)
            self.assertEqual(browser.navigation.directory, provider.root)
            browser.view_selector.setCurrentIndex(1)
            self.assertEqual(browser.views.root, provider.root)
            self.wait_until(lambda: provider.root / 'image.png' in browser.views.covers.icons)
            self.assertFalse(browser.views.covers.icons[provider.root / 'image.png'].isNull())
            browser.filter.setText('note')
            self.wait_until(lambda: not browser.busy)
            self.assertEqual(browser.tree.topLevelItemCount(), 1)
            self.assertEqual(browser.tree.topLevelItem(0).text(0), 'note.txt')
            browser.stop()
            self.wait_until(lambda: not browser.busy)
            browser.close()

    def test_picker_waits_for_thumbnail_before_releasing_source_on_cancel(self):
        provider = MemoryProvider()
        entered, finish = Event(), Event()
        self.addCleanup(finish.set)
        def thumbnail(path, size, cancelled):
            entered.set()
            finish.wait(3)
            return provider.data
        provider.thumbnail = thumbnail
        released = []
        picker = ResourcePicker([('Private', lambda: (provider, lambda: released.append('closed'))),
                                 ('Other', lambda: (MemoryProvider(), lambda: None))])
        self.addCleanup(picker.deleteLater)
        picker.show()
        self.wait_until(lambda: not picker.browser.busy)
        picker.browser.view_selector.setCurrentIndex(1)
        self.wait_until(entered.is_set)
        picker.switch(1)
        self.assertEqual(picker.active_index, 0)
        picker.reject()
        self.assertEqual(released, [])
        finish.set()
        self.wait_until(lambda: released == ['closed'])
        self.assertFalse(picker.browser.busy)
        self.assertEqual(len(picker.browser.views.covers.icons), 0)

    def test_picker_can_choose_during_thumbnail_loading_and_waits_before_accepting(self):
        provider = MemoryProvider()
        entered, finish = Event(), Event()
        self.addCleanup(finish.set)
        def thumbnail(path, size, cancelled):
            entered.set()
            finish.wait(3)
            return provider.data
        provider.thumbnail = thumbnail
        released = []
        picker = ResourcePicker([('Storage', lambda: (provider, lambda: released.append(True)))], name='image.png')
        self.addCleanup(picker.deleteLater)
        picker.show()
        self.wait_until(lambda: not picker.browser.busy)
        picker.browser.view_selector.setCurrentIndex(1)
        self.wait_until(entered.is_set)
        picker.choose()
        self.wait_until(lambda: not picker.operation.busy)
        self.assertIsNone(picker.choice)
        self.assertEqual(released, [])
        finish.set()
        self.wait_until(lambda: picker.choice is not None)
        self.assertEqual(picker.choice.path, 'image.png')
        self.assertFalse(picker.browser.busy)
        picker.choice.close()
        self.assertEqual(released, [True])
