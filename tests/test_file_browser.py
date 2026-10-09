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
                BrowserPanel('additional', 'Additional Information',
                             lambda: BrowserDetails((('Additional', 'available'),))))

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

    def test_search_results_locate_file_and_keep_worker_safe(self):
        window = self.browser.open_search()
        window.query.setText('ITEM')
        window.run_search()
        deadline = time.monotonic() + 5
        while window.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.01)
        self.assertEqual(window.results.topLevelItemCount(), 1)
        window.locate(self.path)
        self.assertEqual(self.browser.selected_objects()[0].path, self.path)
        window.close()
        self.wait()

    def test_storage_totals_treemap_and_drilldown(self):
        folder = self.root / 'large'
        folder.mkdir()
        (folder / 'large.bin').write_bytes(b'x' * 1000)
        window = self.browser.open_storage()
        window.scan(True)
        deadline = time.monotonic() + 5
        while window.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.01)
        self.assertGreaterEqual(window.totals[self.root], 1003)
        window.drill(folder)
        self.app.processEvents()
        self.assertEqual(window.results.topLevelItemCount(), 1)
        self.assertEqual(window.totals[folder], 1000)
        self.assertTrue(window.up_button.isEnabled())
        from commonUtils.ui.file_browser.storage import treemap_rectangles
        rects = treemap_rectangles([(self.path, 1), (folder, 3)], qt.QRectF(0, 0, 400, 200))
        self.assertEqual(sum(rect.width() * rect.height() for _, _, rect in rects), 80000)
        self.assertFalse(rects[0][2].intersects(rects[1][2]))
        window.close()
        self.wait()

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
        self.assertEqual([action.text() for action in menu.actions() if not action.isSeparator()],
                         ['Open in Default App', 'Cut', 'Copy', 'Rename', menu.actions()[-1].text()])
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
        self.assertEqual(self.browser.tabs.count(), 3)
        self.assertIn('Project value: Test value', self.browser.tabs.widget(1).toPlainText())
        self.assertIn('Path:', self.browser.tabs.widget(0).toPlainText())
        menu = self.browser.context_menu_for(index)
        next(action for action in menu.actions() if action.text() == 'Project Action').trigger()
        self.assertEqual(len(self.calls), 1)
        self.assertIsInstance(self.calls[0][0], CustomFile)
        self.browser._activate(index)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([self.browser.tabs.tabText(index) for index in range(self.browser.tabs.count())],
                         ['File Information', 'Example Information', 'Additional Information'])
        self.assertIn('Additional: available', self.browser.preview.toPlainText())
        self.assertNotIn('Panels', [button.text() for button in self.browser.findChildren(qt.QToolButton)])
        self.browser.refresh()
        self.wait()
        self.assertEqual(self.browser.tabs.count(), 3)
        menu.deleteLater()

    def test_mixed_selection_groups_and_deduplicates_feature_actions(self):
        registration = register_file_type(CustomFile, 'project')
        self.addCleanup(file_types.unregister, registration)
        self.browser.action_providers = (lambda item, context: (
            BrowserAction('example.action', 'Duplicate', lambda ctx: None, source='Example'),
            BrowserAction('example.second', 'Second Action', lambda ctx: None, source='Example')),)
        self.select(self.path)
        other = self.browser.model.index(str(self.root / 'other.bin'))
        self.browser.tree.selectionModel().select(other,
            qt.QItemSelectionModel.SelectionFlag.Select | qt.QItemSelectionModel.SelectionFlag.Rows)
        menu = self.browser.context_menu_for(other)
        labels = [action.text() for action in menu.actions()]
        self.assertEqual(labels.count('Project Action'), 1)
        self.assertNotIn('Duplicate', labels)
        self.assertEqual(labels.count('Second Action'), 1)
        self.assertIn('Extensions', labels)
        self.assertIn('Example', labels)
        project = next(action for action in menu.actions() if action.text() == 'Project Action')
        project.trigger()
        self.assertEqual({item.path for item in self.calls[-1]}, {self.path, self.root / 'other.bin'})
        self.assertEqual(project.property('source'), 'Extensions')
        menu.deleteLater()

    def test_extension_layers_are_reversible_and_restore_previous_handlers(self):
        called = []
        first = lambda: called.append('first')
        second = lambda: called.append('second')
        self.browser.install_extension('first', services={'shared': first})
        self.browser.install_extension('second', services={'shared': second},
            action_providers=(lambda item, context: (BrowserAction('second.action', 'Second',
                lambda ctx: ctx.invoke('shared'), source='Second'),),))
        self.browser.services['shared']()
        self.assertEqual(called, ['second'])
        self.browser.set_extension_enabled('second', False)
        self.browser.services['shared']()
        self.assertEqual(called[-1], 'first')
        self.assertNotIn('Second', [action.text() for action in self.browser.context_menu_for(
            self.browser.model.index(str(self.path))).actions()])
        self.browser.set_extension_enabled('second', True)
        self.browser.services['shared']()
        self.assertEqual(called[-1], 'second')
        self.browser.remove_extension('second')
        self.browser.remove_extension('first')
        self.assertNotIn('shared', self.browser.services)
        self.assertIn('example.action', self.browser.services)
        self.wait()

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
        menu = self.browser.context_menu_for(index)
        self.assertEqual([action.text() for action in menu.actions() if not action.isSeparator()][:-1],
                         ['Open', 'Cut', 'Copy', 'Paste', 'Rename'])
        self.assertTrue(menu.actions()[-1].text().startswith('Reveal in '))
        menu.deleteLater()
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

    def test_breadcrumbs_contain_only_root_and_folders_and_navigate_ancestors(self):
        folder = self.root / 'series' / 'volume'
        folder.mkdir(parents=True)
        comic = folder / 'nested.project'
        comic.write_text('test')
        self.browser.navigate(folder)
        self.select(comic)
        navigation = self.browser.navigation
        self.assertEqual(navigation.breadcrumbs.paths, [self.root, folder.parent, folder])
        self.assertEqual([button.text() for button in navigation.breadcrumbs.buttons],
                         [self.root.name, 'series', 'volume'])
        self.assertNotIn(comic, navigation.breadcrumbs.paths)
        navigation.breadcrumbs.buttons[1].click()
        self.assertEqual(self.browser.views.root, folder.parent)
        navigation.back.click()
        self.assertEqual(self.browser.views.root, folder)
        navigation.forward.click()
        self.assertEqual(self.browser.views.root, folder.parent)
        navigation.breadcrumbs.buttons[0].click()
        self.assertEqual(self.browser.views.root, self.root)
        self.assertFalse(navigation.up.isEnabled())
        navigation.set_directory(comic)
        self.assertEqual(navigation.directory, self.root)
        self.assertEqual(navigation.breadcrumbs.paths, [self.root])

    def test_structured_fields_are_selectable_plain_text_and_use_model_folder_icon(self):
        folder = self.root / 'custom folder'
        folder.mkdir()
        icon = qt.QPixmap(96, 96)
        icon.fill(qt.QColor('#d98c31'))
        with patch.object(self.browser.model, 'fileIcon', return_value=qt.QIcon(icon)) as provider:
            self.select(folder)
            self.assertTrue(provider.called)
            actual = self.browser.cover.pixmap().toImage().pixelColor(20, 20)
            self.assertEqual(actual, qt.QColor('#d98c31'))
        panel = self.browser.preview
        from commonUtils.ui.file_browser.details import DetailsPanel
        self.assertIsInstance(panel, DetailsPanel)
        values = [label for label in panel.findChildren(qt.QLabel) if label.accessibleName() == 'Path']
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].text(), str(folder))
        self.assertEqual(values[0].textFormat(), qt.Qt.TextFormat.PlainText)
        self.assertTrue(values[0].hasHeightForWidth())
        wide = values[0].fontMetrics().horizontalAdvance(values[0].text()) + 20
        self.assertGreater(values[0].heightForWidth(100), values[0].heightForWidth(wide))
        self.assertTrue(values[0].textInteractionFlags() & qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.assertLessEqual(self.browser.cover.maximumHeight(), 120)

    def test_icon_view_switches_and_responsive_grid_fills_the_viewport(self):
        selector = self.browser.view_selector
        self.assertFalse(isinstance(selector, qt.QComboBox))
        self.assertEqual(list(selector.buttons), [1, 0, 2])
        for mode in (1, 2, 0):
            selector.buttons[mode].click()
            self.assertEqual(self.browser.views.currentIndex(), mode)
            self.assertEqual(selector.currentIndex(), mode)
            self.assertTrue(selector.buttons[mode].isChecked())
            self.assertFalse(selector.buttons[mode].icon().isNull())
        tiles = self.browser.views.tiles
        self.browser.views.set_mode(1)
        for width in (640, 820, 1060):
            self.browser.resize(width + 500, 800)
            self.app.processEvents()
            tiles.fit_grid()
            usable = tiles.viewport().width() - 2
            columns = max(1, usable // 99)
            self.assertLess(usable - columns * tiles.gridSize().width(), columns)
            self.assertEqual(tiles.iconSize().width(), min(71, max(16, tiles.gridSize().width() - 28)))

    def test_column_files_end_the_trail_without_an_extra_preview(self):
        from commonUtils.ui.file_browser.views import ColumnDelegate
        self.browser.view_selector.setCurrentIndex(2)
        columns = self.browser.views.columns
        index = self.browser.model.index(str(self.path))
        columns.selectionModel().setCurrentIndex(index, qt.QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.wait()
        if hasattr(columns, 'isPreviewColumnVisible'):
            self.assertFalse(columns.isPreviewColumnVisible())
        else:
            host = columns.previewWidget().parentWidget().parentWidget()
            self.assertEqual(host.width(), 0)
            self.assertEqual(host.maximumWidth(), 0)
        self.assertEqual(columns.viewport().backgroundRole(), qt.QPalette.ColorRole.Window)
        children = [view for view in columns.findChildren(qt.QListView) if view.isVisible()]
        self.assertTrue(children)
        self.assertTrue(all(isinstance(view.itemDelegate(), ColumnDelegate) for view in children))
        self.assertEqual(self.browser.selected_objects()[0].path, self.path)

    def test_folder_grid_is_small_adjustable_and_immediate_in_nested_folders(self):
        folder = self.root / 'folders'
        folder.mkdir()
        for row in range(60):
            (folder / f'folder-{row:02d}').mkdir()
        tiles = self.browser.views.tiles
        self.browser.view_selector.setCurrentIndex(1)
        mixed_size = tiles.iconSize().width()
        self.browser.navigate(folder)
        deadline = time.monotonic() + 5
        while tiles.model().rowCount(tiles.rootIndex()) < 60 and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertEqual(tiles.model().rowCount(tiles.rootIndex()), 60)
        self.assertTrue(tiles.folders_only)
        self.assertEqual(self.browser.folder_size_slider.value(), 50)
        self.assertEqual(tiles.iconSize().width(), mixed_size)
        self.assertEqual(tiles.iconSize().height(), tiles.iconSize().width())
        for width in (430, 610, 810):
            self.browser.resize(width + 500, 800)
            self.app.processEvents()
            root = tiles.rootIndex()
            usable = tiles.viewport().width() - 2
            columns = max(1, usable // 99)
            self.assertLess(usable - columns * tiles.gridSize().width(), columns)
            first_row = [tiles.visualRect(tiles.model().index(row, 0, root)) for row in range(columns)]
            self.assertTrue(all(rect.top() == first_row[0].top() for rect in first_row))
            next_row = tiles.visualRect(tiles.model().index(columns, 0, root))
            self.assertGreater(next_row.top(), first_row[0].top())
        small = tiles.iconSize().width()
        self.browser.folder_size_slider.setValue(100)
        self.assertGreater(tiles.iconSize().width(), small * 1.5)
        self.assertTrue(self.browser.folder_size_button.isVisible())
        self.browser.view_selector.setCurrentIndex(0)
        self.assertFalse(self.browser.folder_size_button.isVisible())

    def test_size_control_scales_mixed_files_and_bounds_icons_in_narrow_views(self):
        tiles = self.browser.views.tiles
        self.browser.view_selector.setCurrentIndex(1)
        self.assertFalse(tiles.folders_only)
        sizes = []
        for percent in (25, 50, 100):
            self.browser.folder_size_slider.setValue(percent)
            self.app.processEvents()
            sizes.append(tiles.iconSize().width())
            self.assertLessEqual(tiles.iconSize().width(), round(142 * percent / 100))
        self.assertEqual(sizes, [36, 71, 142])
        self.assertLessEqual(tiles.folder_icon_size.width(), tiles.iconSize().width())
        tiles.resize(100, 300); tiles.fit_grid()
        self.assertLessEqual(tiles.iconSize().width(), 142)

    def test_cached_covers_and_oversized_app_icons_respect_size_and_retina_bounds(self):
        class OversizedIconEngine(qt.QIconEngine):
            def actualSize(self, size, mode, state):
                return qt.QSize(512, 512)

            def pixmap(self, size, mode, state):
                pixmap = qt.QPixmap(512, 512)
                pixmap.fill(qt.QColor('orange'))
                return pixmap

            def paint(self, painter, rect, mode, state):
                painter.fillRect(rect, qt.QColor('orange'))

        tiles = self.browser.views.tiles
        self.browser.view_selector.setCurrentIndex(1)
        covers = self.browser.views.covers
        index = covers.mapFromSource(self.browser.model.index(str(self.path)))
        cover = qt.QPixmap(600, 1200); cover.fill(qt.QColor('orange'))
        fallback = qt.QPixmap(16, 16); fallback.fill(qt.QColor('orange'))
        icons = [qt.QIcon(cover), qt.QIcon(OversizedIconEngine()), qt.QIcon(fallback)]
        original = type(covers).data
        for icon in icons:
            def data(model, index, role=qt.Qt.ItemDataRole.DisplayRole):
                return icon if role == qt.Qt.ItemDataRole.DecorationRole else original(model, index, role)
            with patch.object(type(covers), 'data', data):
                for ratio in (1.0, 2.0):
                    with patch.object(tiles, 'devicePixelRatioF', return_value=ratio):
                        for percent in (25, 50, 100):
                            self.browser.folder_size_slider.setValue(percent)
                            option = qt.QStyleOptionViewItem()
                            option.decorationSize = tiles.iconSize()
                            tiles.itemDelegate().initStyleOption(option, index)
                            self.assertFalse(option.icon.isNull())
                            self.assertLessEqual(option.decorationSize.width(), tiles.iconSize().width())
                            self.assertLessEqual(option.decorationSize.height(), tiles.iconSize().height())
                            pixmap = option.icon.pixmap(tiles.iconSize(), ratio)
                            self.assertLessEqual(pixmap.width(), round(tiles.iconSize().width() * ratio))
                            self.assertLessEqual(pixmap.height(), round(tiles.iconSize().height() * ratio))
                            self.assertEqual(option.decorationSize, tiles.iconSize())
                            self.assertAlmostEqual(max(pixmap.width() / (tiles.iconSize().width() * ratio),
                                                       pixmap.height() / (tiles.iconSize().height() * ratio)),
                                                   1.0, delta=.03)
                            if icon is icons[0]:
                                self.assertAlmostEqual(pixmap.width() / pixmap.height(), .5, delta=.03)

    def test_thumbnail_resolution_accounts_for_device_pixel_ratio(self):
        covers = self.browser.views.covers
        path = str(self.path)
        small = qt.QPixmap(120, 165)
        small.fill(qt.QColor('orange'))
        buffer = qt.QBuffer()
        buffer.open(qt.QIODevice.OpenModeFlag.WriteOnly)
        small.save(buffer, 'PNG')
        covers.requested.add(path)
        covers.complete(path, bytes(buffer.data()))
        covers.set_resolution(qt.QSize(180, 248), 2.0)
        self.assertEqual(covers.render_size, (360, 496))
        self.assertNotIn(path, covers.icons)
        self.assertNotIn(path, covers.requested)
        large = qt.QPixmap(360, 496)
        large.fill(qt.QColor('orange'))
        buffer = qt.QBuffer()
        buffer.open(qt.QIODevice.OpenModeFlag.WriteOnly)
        large.save(buffer, 'PNG')
        covers.complete(path, bytes(buffer.data()), 2.0, (360, 496))
        self.assertEqual(covers.resolutions[path], (360, 496))
        self.assertFalse(covers.icons[path].isNull())

    def test_disabling_folder_totals_cancels_scan_and_discards_late_results(self):
        from threading import Event
        from commonUtils.filesystem import FolderStats
        entered, release = Event(), Event()
        self.browser.set_folder_sizes_enabled(False)
        def scan(root, cancelled):
            entered.set()
            release.wait(5)
            return {root: FolderStats(files=999)}
        with patch('commonUtils.ui.file_browser.scan_folders', side_effect=scan):
            try:
                self.browser.set_folder_sizes_enabled(True)
                self.assertTrue(entered.wait(2))
                self.browser.set_folder_sizes_enabled(False)
                self.assertTrue(self.browser.folder_operation.isInterruptionRequested())
            finally:
                release.set()
                self.wait()
        self.assertEqual(self.browser.model.folder_totals, {})
        details = self.browser._generic_details(Directory(self.root), None)
        self.assertIn(('Total size', 'Not calculated'), details.fields)
