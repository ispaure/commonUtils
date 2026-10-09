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
        stable = 0
        while time.monotonic() < deadline:
            self.app.processEvents()
            pending = (self.browser.busy or self.browser.folder_busy or self.browser.views.cover_busy
                       or self.browser.views._column_selection_pending)
            stable = 0 if pending else stable + 1
            if stable >= 2:
                break
            time.sleep(.01)
        self.assertFalse(self.browser.busy or self.browser.folder_busy or self.browser.views._column_selection_pending)

    def test_search_results_locate_file_and_keep_worker_safe(self):
        from commonUtils.directory_index import DirectoryCache
        support = Path(self.enterContext(TemporaryDirectory()))
        cache = DirectoryCache(database=support / 'search-fixture.sqlite3')
        cache.get(self.root, refresh=True)
        with patch('commonUtils.ui.file_browser.index_search.directory_cache', cache):
            search = self.browser.open_search()
            self.browser.search_bar.setText('ITEM')
            deadline = time.monotonic() + 5
            while search.busy or search.debounce.isActive():
                self.assertLess(time.monotonic(), deadline)
                self.app.processEvents()
                time.sleep(.01)
            self.assertEqual(search.results.topLevelItemCount(), 1)
            self.assertTrue(search.show_in_browser(self.path))
            self.assertEqual(self.browser.selected_objects()[0].path, self.path)
            self.assertTrue(self.browser.search_panel.isHidden())
            self.wait()

    def test_storage_totals_treemap_and_drilldown(self):
        folder = self.root / 'large'
        folder.mkdir()
        (folder / 'large.bin').write_bytes(b'x' * 1000)
        self.browser.refresh()
        self.wait()
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
                         ['Open in Default App', 'Cut', 'Copy', 'Rename', 'Move to Trash / Recycle Bin…', menu.actions()[-1].text()])
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
                         ['Open', 'Cut', 'Copy', 'Paste', 'Rename', 'Move to Trash / Recycle Bin…'])
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
        self.assertEqual(list(selector.buttons), [1, 0, 2, 3, 4])
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

    def test_column_single_click_opens_file_information(self):
        from PySide6.QtTest import QTest
        self.browser.view_selector.setCurrentIndex(2)
        self.browser.resize(1000, 650)
        self.wait()
        columns = self.browser.views.columns
        index = self.browser.model.index(str(self.path))
        child = next(view for view in columns.findChildren(qt.QListView)
                     if view.isVisible() and view.rootIndex() == index.parent())
        QTest.mouseClick(child.viewport(), qt.Qt.MouseButton.LeftButton,
                         pos=child.visualRect(index).center())
        self.wait()
        self.assertEqual(self.browser.selected_object.path, self.path)
        self.assertTrue(self.browser.preview_panel.isVisible())
        self.assertTrue(columns.preview_host.isVisible())
        self.assertGreater(columns.preview_host.width(), 0)
        self.assertGreater(self.browser.tabs.count(), 0)

    def test_tiles_sort_names_naturally_independent_of_list_sort(self):
        for name in ('zeta.txt', 'Alpha.txt', 'file10.txt', 'file2.txt'):
            (self.root/name).write_text('text')
        for name in ('Folder10', 'Folder2'):
            (self.root/name).mkdir()
        self.browser.tree.sortByColumn(3, qt.Qt.SortOrder.DescendingOrder)
        self.browser.view_selector.setCurrentIndex(1)
        tiles = self.browser.views.tiles
        deadline = time.monotonic()+5
        while tiles.model().rowCount(tiles.rootIndex()) != 8:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents(); time.sleep(.01)
        names = [tiles.model().data(tiles.model().index(row,0,tiles.rootIndex())) for row in range(8)]
        self.assertEqual(names, ['Folder2','Folder10','Alpha.txt','file2.txt','file10.txt','item.project','other.bin','zeta.txt'])

    def test_entering_columns_keeps_opened_folder_in_first_column(self):
        folder = self.root/'Folder'; folder.mkdir()
        (folder/'inside.txt').write_text('inside')
        self.browser.navigate(folder); self.wait()
        self.browser.view_selector.setCurrentIndex(2); self.wait()
        columns = self.browser.views.columns
        self.assertEqual(Path(self.browser.model.filePath(columns.rootIndex())), self.root)
        self.assertEqual(Path(self.browser.model.filePath(columns.currentIndex())), folder)
        self.assertEqual(self.browser.navigation.directory, folder)
        deadline = time.monotonic()+3
        while not any(view.isVisible() and self.browser.model.filePath(view.rootIndex()) == str(folder)
                      for view in columns.findChildren(qt.QListView)):
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents(); time.sleep(.01)

    def test_column_file_preview_returns_on_single_click_after_folder_selection(self):
        from PySide6.QtTest import QTest
        folder = self.root/'Folder'; folder.mkdir()
        target = folder/'inside.txt'; target.write_text('inside')
        self.browser.view_selector.setCurrentIndex(2); self.wait()
        def click(path):
            index = self.browser.model.index(str(path))
            deadline = time.monotonic()+3
            while True:
                column = next((view for view in self.browser.views.columns.findChildren(qt.QListView)
                               if view.isVisible() and view.rootIndex() == index.parent()), None)
                if column is not None and column.visualRect(index).isValid():
                    break
                self.assertLess(time.monotonic(), deadline)
                self.app.processEvents(); time.sleep(.01)
                index = self.browser.model.index(str(path))
            QTest.mouseClick(column.viewport(), qt.Qt.MouseButton.LeftButton, pos=column.visualRect(index).center())
            self.wait()
        for path in (self.path, folder, target, self.path):
            click(path)
            if path != folder:
                self.assertEqual(self.browser.selected_object.path, path)
                self.assertTrue(self.browser.views.columns.preview_host.isVisible())
                self.assertTrue(self.browser.preview_panel.isVisible())

    def test_columns_preserve_explicit_multi_selection(self):
        from PySide6.QtTest import QTest
        folder = self.root/'Folder'; folder.mkdir()
        (folder/'inside.txt').write_text('inside')
        self.browser.view_selector.setCurrentIndex(2); self.wait()
        columns = self.browser.views.columns
        first = self.browser.model.index(str(self.path))
        second = self.browser.model.index(str(self.root/'other.bin'))
        view = next(view for view in columns.findChildren(qt.QListView)
                    if view.isVisible() and view.rootIndex() == first.parent())
        directory = self.browser.model.index(str(folder))
        QTest.mouseClick(view.viewport(),qt.Qt.MouseButton.LeftButton,pos=view.visualRect(directory).center())
        self.wait()
        first = self.browser.model.index(str(self.path))
        second = self.browser.model.index(str(self.root/'other.bin'))
        QTest.mouseClick(view.viewport(),qt.Qt.MouseButton.LeftButton,pos=view.visualRect(first).center())
        self.wait()
        QTest.mouseClick(view.viewport(),qt.Qt.MouseButton.LeftButton,qt.Qt.KeyboardModifier.ControlModifier,
                         pos=view.visualRect(second).center())
        self.wait()
        self.assertEqual({item.path for item in self.browser.selected_objects()}, {self.path,self.root/'other.bin'})

    def test_column_files_end_the_trail_with_a_matching_preview_column(self):
        from commonUtils.ui.file_browser.views import ColumnDelegate
        self.browser.view_selector.setCurrentIndex(2)
        columns = self.browser.views.columns
        index = self.browser.model.index(str(self.path))
        columns.selectionModel().setCurrentIndex(index, qt.QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.wait()
        if hasattr(columns, 'isPreviewColumnVisible'):
            self.assertTrue(columns.isPreviewColumnVisible())
        host = columns.previewWidget().parentWidget().parentWidget()
        self.assertEqual(host.width(), columns.columnWidths()[0])
        self.assertEqual(self.browser.preview_panel.parentWidget(), columns.preview_container)
        self.assertFalse(self.browser.preview_panel.isHidden())
        self.assertTrue(self.browser.preview_toggle.isHidden())
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
        self.assertTrue(self.browser.folder_size_button.isVisible())
        self.assertEqual(self.browser.tree.iconSize(), qt.QSize(32, 32))
        self.browser.view_selector.setCurrentIndex(2)
        self.app.processEvents()
        self.assertTrue(self.browser.views.columns.findChildren(qt.QListView))
        self.assertTrue(all(column.iconSize() == qt.QSize(32, 32)
                            for column in self.browser.views.columns.findChildren(qt.QListView)))

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
                                # The icon now includes a centered transparent canvas;
                                # measure the artwork rather than the canvas ratio.
                                image = pixmap.toImage()
                                pixels = [(x,y) for y in range(image.height()) for x in range(image.width())
                                          if image.pixelColor(x,y).alpha() > 128]
                                width = max(x for x,y in pixels) - min(x for x,y in pixels) + 1
                                height = max(y for x,y in pixels) - min(y for x,y in pixels) + 1
                                self.assertAlmostEqual(width / height, .5, delta=.03)

    def test_tile_paint_preserves_square_wide_and_portrait_images(self):
        tiles = self.browser.views.tiles
        self.browser.view_selector.setCurrentIndex(1)
        covers = self.browser.views.covers
        index = covers.mapFromSource(self.browser.model.index(str(self.path)))
        original = type(covers).data
        for width, height in [(200, 200), (400, 200), (200, 400)]:
            pixmap = qt.QPixmap(width, height); pixmap.fill(qt.QColor('#ff00ff'))
            icon = qt.QIcon(pixmap)
            def data(model, item, role=qt.Qt.ItemDataRole.DisplayRole):
                return icon if role == qt.Qt.ItemDataRole.DecorationRole else original(model, item, role)
            with patch.object(type(covers), 'data', data):
                image = qt.QImage(200, 240, qt.QImage.Format.Format_ARGB32)
                image.fill(qt.QColor('white'))
                option = qt.QStyleOptionViewItem(); option.rect = qt.QRect(0, 0, 200, 240)
                option.widget = tiles; option.decorationPosition = qt.QStyleOptionViewItem.Position.Top
                option.decorationAlignment = qt.Qt.AlignmentFlag.AlignCenter
                painter = qt.QPainter(image)
                tiles.itemDelegate().paint(painter, option, index); painter.end()
                pixels = [(x,y) for y in range(240) for x in range(200)
                          if image.pixelColor(x,y).name() == '#ff00ff']
                self.assertTrue(pixels)
                actual_width = max(x for x,y in pixels)-min(x for x,y in pixels)+1
                actual_height = max(y for x,y in pixels)-min(y for x,y in pixels)+1
                self.assertAlmostEqual(actual_width/actual_height, width/height, delta=.08)

    def test_native_icon_engine_is_not_asked_to_rasterize_a_portrait_canvas(self):
        class NativeEngine(qt.QIconEngine):
            def actualSize(self,size,mode,state):return size
            def pixmap(self,size,mode,state):
                image=qt.QPixmap(size);image.fill(qt.QColor('magenta'));return image
            def paint(self,painter,rect,mode,state):painter.fillRect(rect,qt.QColor('magenta'))
        tiles=self.browser.views.tiles;self.browser.view_selector.setCurrentIndex(1)
        covers=self.browser.views.covers;index=covers.mapFromSource(self.browser.model.index(str(self.path)))
        icon=qt.QIcon(NativeEngine());original=type(covers).data
        def data(model,item,role=qt.Qt.ItemDataRole.DisplayRole):
            return icon if role==qt.Qt.ItemDataRole.DecorationRole else original(model,item,role)
        with patch.object(type(covers),'data',data):
            option=qt.QStyleOptionViewItem();option.decorationSize=tiles.iconSize()
            tiles.itemDelegate().initStyleOption(option,index)
            image=option.icon.pixmap(tiles.iconSize())
            image = image.toImage()
            pixels = [(x,y) for y in range(image.height()) for x in range(image.width())
                      if image.pixelColor(x,y).alpha() > 128]
            self.assertEqual(max(x for x,y in pixels)-min(x for x,y in pixels),
                             max(y for x,y in pixels)-min(y for x,y in pixels))

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

    def test_pausing_indexing_preserves_cached_totals_and_discards_late_results(self):
        from threading import Event
        from commonUtils.filesystem import FolderStats
        entered, release = Event(), Event()
        self.browser.set_folder_sizes_enabled(False)
        saved = dict(self.browser.model.folder_totals)
        def scan(root, cancelled, **kwargs):
            entered.set()
            release.wait(5)
            from unittest.mock import Mock
            return Mock(folder_stats=lambda **kwargs: {root: FolderStats(files=999)})
        with patch('commonUtils.directory_index.directory_cache.reconcile_folder', side_effect=scan):
            try:
                self.browser.set_folder_sizes_enabled(True)
                self.assertTrue(entered.wait(2))
                self.browser.set_folder_sizes_enabled(False)
                self.assertTrue(self.browser.folder_operation.isInterruptionRequested())
            finally:
                release.set()
                self.wait()
        self.assertEqual(self.browser.model.folder_totals, saved)
        details = self.browser._generic_details(Directory(self.root), None)
        self.assertIn(('Total size', 'Not calculated'), details.fields)
