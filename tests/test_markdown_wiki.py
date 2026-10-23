"""Directory landing pages, title rules, search ancestry and editor navigation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from commonUtils.formats.markdown.wiki import MarkdownWiki
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer, open_markdown
from commonUtils.filesystem.directories import Directory


class WikiCatalogTests(unittest.TestCase):
    def test_landing_title_search_and_links(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            folder = root / 'test'
            folder.mkdir()
            (folder / 'test.md').write_text('# Apple\n\nSpecial fruit')
            (folder / 'child.md').write_text('# Child\n\nNeedle in source')
            (root / 'blank.md').write_text('\n# After blank')
            (root / 'metadata.md').write_text('---\nx: y\n---\n# After properties')
            (root / 'setext.md').write_text('Setext title\n====\n')
            (root / 'linked').symlink_to(folder, target_is_directory=True)
            catalog = MarkdownWiki(Directory(root))
            parent = next(e for e in catalog.entries if e.location == folder)
            self.assertEqual(parent.title, 'Apple')
            self.assertEqual(parent.page, folder / 'test.md')
            self.assertEqual(catalog.parent_page(folder / 'child.md'), folder / 'test.md')
            self.assertIsNone(catalog.parent_page(folder / 'test.md'))
            self.assertEqual([e.title for e in parent.children], ['Child'])
            self.assertEqual(catalog.search('apple')[0].page, folder / 'test.md')
            self.assertEqual(catalog.search('needle', 'content')[0].children[0].page, folder / 'child.md')
            self.assertEqual(catalog.search('missing'), ())
            names = {e.title for e in catalog.entries}
            self.assertTrue({'After blank', 'After properties', 'Setext title'} <= names)
            self.assertFalse(any(e.location.name == 'linked' for e in catalog.entries))

    def test_same_named_root_is_single_parent_and_search_keeps_ancestry(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / 'docs'
            root.mkdir()
            home, child = root / 'docs.md', root / 'child.md'
            home.write_text('# Documentation')
            child.write_text('# Child\nNeedle')
            catalog = MarkdownWiki(root)
            self.assertEqual(len(catalog.entries), 1)
            entry = catalog.entries[0]
            self.assertEqual((entry.location, entry.page), (root, home))
            self.assertEqual([e.page for e in entry.children], [child])
            self.assertEqual(catalog.search('needle', 'content')[0].children[0].page, child)
            self.assertEqual(catalog.parent_page(child), home)
            self.assertIsNone(catalog.parent_page(home))

    def test_heading_after_properties_and_blank_lines(self):
        for text in ('---\ntags: [fruit]\n---\n# Apple',
                     '---\n# YAML comment\ntags: [fruit]\n---\n\n\n# Apple ##',
                     '\ufeff---\ntitle: Other\n---\r\n\r\nApple\r\n====',
                     '\n   \n# Apple',
                     '---\ntags: [fruit]\n...\n\n# Apple'):
            with self.subTest(text=text):
                self.assertEqual(MarkdownWiki.title(text, 'fallback'), 'Apple')
        for text in ('---\ntags: [fruit]\n# YAML comment without closing delimiter',
                     '---\ntags: [fruit]\n---\nIntroduction\n\n# Later heading',
                     '---\ntags: [fruit]\n---\n\n',
                     '    # Indented code'):
            with self.subTest(text=text):
                self.assertEqual(MarkdownWiki.title(text, 'fallback'), 'fallback')


class WikiViewerTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_repopulation_retires_referenced_items_without_a_pending_reset(self):
        with self.temporary_directory() as temporary:
            root = Path(temporary).resolve()
            first, second = root / 'first.md', root / 'second.md'
            first.write_text('# First')
            second.write_text('# Second')
            viewer = MarkdownViewer(first, directory=root)
            panel = viewer.wiki
            old = [panel.tree.topLevelItem(i) for i in range(panel.tree.topLevelItemCount())]
            panel.search.setText('Second')
            self.assertTrue(panel.timer.isActive())
            panel.populate()
            self.assertFalse(panel.timer.isActive())
            self.assertTrue(all(item.treeWidget() is None for item in old))
            self.assertEqual({item.text(0) for item in old}, {'First', 'Second'})
            self.assertEqual(panel.tree.topLevelItemCount(), 1)
            target = panel.tree.topLevelItem(0)
            panel.open_item(target)
            self.assertEqual(viewer.current_path, second)
            self.assertIs(panel.tree.currentItem(), target)
            viewer.close()

    def test_arrow_selection_opens_page_and_cancel_restores_selection(self):
        from PySide6.QtTest import QTest
        with self.temporary_directory() as temporary:
            root = Path(temporary).resolve() / 'docs'
            root.mkdir()
            home, child = root / 'docs.md', root / 'child.md'
            home.write_text('# Documentation')
            child.write_text('# Child')
            viewer = MarkdownViewer(home, directory=root, allow_edit=True)
            viewer.show()
            tree = viewer.wiki.tree
            self.assertEqual(tree.topLevelItemCount(), 1)
            self.assertTrue(tree.topLevelItem(0).isExpanded())
            tree.setFocus()
            QTest.keyClick(tree, qt.Qt.Key.Key_Down)
            self.assertEqual(viewer.current_path, child)
            self.assertEqual([Path(entry['url'].toLocalFile()) for entry in viewer.history], [home, child])
            viewer.set_edit_mode('source')
            viewer.editor.insertPlainText('Dirty')
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel) as warning:
                QTest.keyClick(tree, qt.Qt.Key.Key_Up)
            self.assertEqual(warning.call_count, 1)
            self.assertEqual(viewer.current_path, child)
            self.assertEqual(tree.currentItem().data(0, qt.Qt.ItemDataRole.UserRole), child)
            self.assertTrue(viewer.is_modified)
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel) as warning:
                QTest.mouseClick(tree.viewport(), qt.Qt.MouseButton.LeftButton,
                                 pos=tree.visualItemRect(tree.topLevelItem(0)).center())
            self.assertEqual(warning.call_count, 1)
            self.assertEqual(viewer.current_path, child)
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard):
                viewer.back()
            self.assertEqual(viewer.current_path, home)
            viewer.close()

    def test_cross_wiki_links_and_history_switch_scope(self):
        with self.temporary_directory() as temporary:
            root = Path(temporary).resolve()
            scopes = [root / name / 'docs' for name in ('app', 'feature')]
            for scope in scopes:
                (scope / 'user').mkdir(parents=True)
                (scope / 'docs.md').write_text('# Documentation')
                (scope / 'user/user.md').write_text('# Usage')
            first, second = [scope / 'user/user.md' for scope in scopes]
            viewer = MarkdownViewer(first, directory=scopes[0])
            viewer.wiki.search.setText('Usage')
            viewer.follow_link(qt.QUrl.fromLocalFile(str(second)))
            self.assertEqual(viewer.wiki.catalog.root, scopes[1])
            self.assertEqual(viewer.wiki.search.text(), '')
            self.assertEqual(viewer.wiki.tree.currentItem().text(0), 'Usage')
            viewer.back()
            self.assertEqual(viewer.current_path, first)
            self.assertEqual(viewer.wiki.catalog.root, scopes[0])
            viewer.forward()
            self.assertEqual(viewer.wiki.catalog.root, scopes[1])
            viewer.close()

    def test_page_click_cancel_and_history_selection(self):
        with self.temporary_directory() as temporary:
            root = Path(temporary).resolve()
            first, second = root / 'README.md', root / 'second.md'
            first.write_text('# First\n\nHome')
            second.write_text('# Second\n\nOther')
            viewer = MarkdownViewer(directory=Directory(root), allow_edit=True)
            self.assertEqual(viewer.current_path, first)
            viewer.set_edit_mode('source')
            viewer.editor.insertPlainText('Dirty')
            target = next(viewer.wiki.tree.topLevelItem(i) for i in range(2)
                          if viewer.wiki.tree.topLevelItem(i).text(0) == 'Second')
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
                viewer.wiki.open_item(target)
            self.assertEqual(viewer.current_path, first)
            self.assertTrue(viewer.is_modified)
            self.assertEqual(viewer.wiki.tree.currentItem().text(0), 'First')
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard):
                viewer.wiki.open_item(target)
            self.assertEqual(viewer.current_path, second)
            viewer.back()
            self.assertEqual(viewer.current_path, first)
            self.assertEqual(viewer.wiki.tree.currentItem().text(0), 'First')
            viewer.wiki.mode.setCurrentIndex(1)
            viewer.wiki.search.setText('Other')
            viewer.wiki.populate()
            self.assertEqual(viewer.wiki.tree.topLevelItemCount(), 1)
            self.assertEqual(viewer.wiki.tree.topLevelItem(0).text(0), 'Second')
            viewer.close()

    def test_window_directory_default_and_no_directory_layout(self):
        with self.temporary_directory() as temporary:
            root = Path(temporary).resolve()
            (root / 'README.md').write_text('# Home')
            window = open_markdown(None, directory=Directory(root), detached=True)
            self.assertEqual(window.viewer.current_path, root / 'README.md')
            self.assertEqual(window.viewer.editor.toPlainText(), '# Home')
            window.close()
            bare = MarkdownViewer()
            self.assertIsNone(bare.wiki)
            bare.close()

    def test_up_parent_landing_root_and_unsaved_cancel(self):
        with self.temporary_directory() as temporary:
            root = Path(temporary).resolve()
            home = root / 'README.md'
            home.write_text('# Home')
            folder = root / 'test'
            folder.mkdir()
            landing = folder / 'test.md'
            landing.write_text('# Apple')
            child = folder / 'child.md'
            child.write_text('# Child')
            viewer = MarkdownViewer(child, directory=root, allow_edit=True)
            self.assertTrue(viewer.wiki.up_button.isEnabled())
            self.assertFalse(viewer.wiki.up_button.icon().isNull())
            viewer.set_edit_mode('source')
            viewer.editor.insertPlainText('dirty')
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.assertFalse(viewer.wiki.go_up())
            self.assertEqual(viewer.current_path, child)
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard):
                viewer.wiki.up_button.click()
            self.assertEqual(viewer.current_path, landing)
            viewer.wiki.up_button.click()
            self.assertEqual(viewer.current_path, home)
            self.assertFalse(viewer.wiki.up_button.isEnabled())
            viewer.back_button.click()
            self.assertEqual(viewer.current_path, landing)
            viewer.forward_button.click()
            self.assertEqual(viewer.current_path, home)
            viewer.close()

    def test_relative_extensionless_pages_and_external_text_editor(self):
        with self.temporary_directory() as temporary:
            root = Path(temporary).resolve()
            folder = root / 'guide'
            folder.mkdir()
            page = folder / 'page.md'
            page.write_text('# Page')
            other = root / 'other.md'
            other.write_text('# Other')
            script = root / 'example.py'
            script.write_text('print("hello")')
            viewer = MarkdownViewer(page, directory=root)
            viewer.follow_link(qt.QUrl('../other'))
            self.assertEqual(viewer.current_path, other)
            viewer.back()
            history = list(viewer.history)
            with patch('commonUtils.ui.text_editor.open_text_file') as opened:
                viewer.follow_link(qt.QUrl('../example.py'))
                opened.assert_called_once_with(script, viewer.window())
            self.assertEqual(viewer.history, history)
            self.assertEqual(viewer.current_path, page)
            viewer.close()

    def test_standalone_linked_text_editor_preserves_close_veto(self):
        from commonUtils.ui.text_editor import open_text_file
        with self.temporary_directory() as temporary:
            path = Path(temporary) / 'script.py'
            path.write_text('print("original")')
            with patch.object(self.app, '_commonutils_open_text_file', None, create=True):
                window = open_text_file(path)
            self.assertEqual(window.editor.text.toPlainText(), 'print("original")')
            window.editor.text.insertPlainText('# change')
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.assertFalse(window.close())
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard):
                self.assertTrue(window.close())
            self.assertEqual(path.read_text(), 'print("original")')
