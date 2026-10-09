"""Recent-file persistence and shared menu dispatch are format independent."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from commonUtils.ui import pyside as qt
from commonUtils.ui.reader_menus import ReaderMenus, RecentFiles


class ReaderMenuTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_history_is_bounded_deduplicated_and_filters_missing_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            history = RecentFiles(path=root / 'cache' / 'recent.json')
            files = []
            for number in range(45):
                path = root / f'{number}.EPUB'
                path.touch()
                files.append(path)
                history.add(path)
            history.add(files[-2])
            paths = history.paths(('.epub',))
            self.assertEqual(len(paths), 40)
            self.assertEqual(paths[0], files[-2])
            self.assertEqual(paths.count(files[-2]), 1)
            files[-2].unlink()
            self.assertNotIn(files[-2], history.paths())
            self.assertEqual(history.paths(('.cbz',)), [])
            self.assertEqual(len(json.loads(history.path.read_text())), 40)

    def test_invalid_history_is_ignored_and_can_be_replaced(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            history = RecentFiles(path=root / 'recent.json')
            for value in ('invalid json', '{}', '[null, "relative.epub"]', 'x' * 65537):
                history.path.write_text(value)
                self.assertEqual(history.paths(), [])
            book = root / 'book.epub'
            book.touch()
            history.add(book)
            self.assertEqual(history.paths(), [book])

    def test_recent_action_opens_its_own_path_and_callbacks_ignore_checked(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            history = RecentFiles(path=root / 'recent.json')
            first, second = root / 'first.epub', root / 'second.cbz'
            first.touch()
            second.touch()
            history.add(first)
            history.add(second)
            owner = qt.QWidget()
            bar = qt.QMenuBar(owner)
            opened, closed, fullscreen = Mock(), Mock(), Mock()
            menus = ReaderMenus(owner, bar, open_file=Mock(), edit_metadata=Mock(),
                                close=closed, fullscreen=fullscreen, open_path=opened,
                                suffixes=('.epub', '.cbz'), history=history)
            menus._refresh_recent()
            actions = menus.recent.actions()
            actions[0].trigger()
            actions[1].trigger()
            self.assertEqual([call.args for call in opened.call_args_list], [(second,), (first,)])
            menus.close_action.trigger()
            menus.fullscreen_action.trigger()
            closed.assert_called_once_with()
            fullscreen.assert_called_once_with()
            self.assertTrue(menus.fullscreen_action.isChecked())
            owner.deleteLater()
