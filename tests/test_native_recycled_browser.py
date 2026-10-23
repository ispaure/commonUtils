"""An independent Toga consumer exercises browser lifetime and bounded rendering."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(importlib.util.find_spec('toga'), 'Optional Toga backend is not installed')
class RecycledBrowserConsumerTests(unittest.TestCase):
    def test_browser_without_consumer_imports(self):
        script = '''
import importlib.abc, sys, asyncio
class Reject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'logisticsmobile', 'features', 'PySide6'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Reject())
import toga
from pathlib import Path
from types import SimpleNamespace
from commonUtils.ui.native.recycled_list import RecycledList, ListAppearance
from commonUtils.ui.native_browser.recycled import RecycledBrowser
app = toga.App('Independent browser', 'org.example.browser')
app.main_window = toga.MainWindow()
opened = []
browser = RecycledBrowser(open_file=opened.append)
provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
rows = [dict(path=f'{i:05}.txt', name=f'{i:05}.txt', directory=False) for i in range(10005)]
try:
    browser.set_entries(provider, '', rows)
    assert isinstance(browser.native_list, RecycledList)
    assert len(browser.native_list.data) == 10005
    assert browser.info in browser.widget.children
    app.loop.run_until_complete(browser.select(browser.entries[0]))
    assert browser.info.children
    assert not browser.buttons and not browser.items.children
    stale = browser.native_list.data[-1]
    browser.set_entries(provider, '', rows)
    app.loop.run_until_complete(browser._activate_row(stale))
    assert not opened
    app.loop.run_until_complete(browser._activate_row(browser.native_list.data[-1]))
    assert opened[-1]['path'] == '10004.txt'
    browser.show_tiles()
    assert len(browser.buttons) <= 80
    old_cards = list(browser._tile_cards.values())
    browser._update_tile_window(10000000)
    assert len(browser.buttons) <= 80
    assert all(card[3].is_set() for card in old_cards)
    assert browser.entries[-1].identity in browser.buttons
    browser.show_list()
    assert len(browser.native_list.data) == 10005
    assert not browser._tile_cards
    browser.open_search()
    assert browser.search_panel.parent is browser.widget
    browser.search.value = '10004'
    app.loop.run_until_complete(asyncio.sleep(.45))
    assert len(browser.native_list.data) == 1
    browser.close_search()
    app.loop.run_until_complete(asyncio.sleep(.45))
    assert len(browser.native_list.data) == 10005
    visible = []
    listing = RecycledList(on_visible=visible.append, appearance=ListAppearance(row_height=56, icon_size=32))
    listing.data = [dict(title='A', subtitle='', folder=False, icon=None)]
    listing.row_visible(0)
    assert visible == [listing.data[0]]
    listing.clear()
    listing.row_visible(0)
    assert len(visible) == 1
    assert listing.icon_size == 32
    try:
        ListAppearance(row_height=0)
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid row height accepted')
finally:
    app.loop.run_until_complete(browser.close())
    app.main_window.close()
    app.loop.close()
assert not browser.tasks and not browser.work.decoded and not browser.native_list.data
'''
        import toga
        root = str(Path(__file__).resolve().parents[2])
        dependencies = str(Path(toga.__file__).resolve().parent.parent)
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((root, dependencies)), TOGA_BACKEND='toga_dummy')
        result = subprocess.run([sys.executable, '-c', script], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
