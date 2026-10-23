"""Native components have no consumer imports and retain explicit ownership."""
import os
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

from commonUtils.ui.native.navigation_state import NavigationState


class NativeComponentTests(unittest.TestCase):
    def test_native_package_retains_the_desktop_dialog_backend(self):
        script = '''
from unittest.mock import patch
from commonUtils import ui
from commonUtils.ui import native
from commonUtils.runtime.platform import OS
from commonUtils.ui.native import dialogs
with patch.object(ui, 'use_pyside', False), patch.object(dialogs, 'get_os', return_value=OS.LINUX), \
     patch.object(dialogs, '_display_msg_box_ok_linux', return_value=True) as ok, \
     patch.object(dialogs, '_display_msg_box_ok_cancel_linux', return_value=False) as cancel:
    assert ui.display_msg_box_ok('Title', 'Message') is True
    assert ui.display_msg_box_ok_cancel('Title', 'Message') is False
    ok.assert_called_once_with('Title', 'Message')
    cancel.assert_called_once_with('Title', 'Message')
'''
        self.run_isolated(script)

    def test_dialog_dispatch_preserves_each_desktop_transport(self):
        from unittest.mock import patch
        from commonUtils.ui.native import dialogs
        from commonUtils.runtime.platform import OS
        for platform, suffix in ((OS.WIN, 'windows'), (OS.MAC, 'macos'), (OS.LINUX, 'linux')):
            for name in ('display_msg_box_ok', 'display_msg_box_ok_cancel'):
                with self.subTest(platform=platform, name=name), \
                     patch.object(dialogs, 'get_os', return_value=platform), \
                     patch.object(dialogs, '_' + name + '_' + suffix, return_value=True) as transport:
                    self.assertTrue(getattr(dialogs, name)('Synthetic title', r'Line\nTwo'))
                    transport.assert_called_once_with('Synthetic title', 'Line\nTwo')

    def test_state_is_configurable_and_each_destination_retains_its_routes(self):
        state = NavigationState(('gallery', 'notes'))
        state.push('picture')
        state.select('notes')
        state.push('draft')
        state.select('gallery')
        self.assertEqual(state.back(), 'picture')
        self.assertEqual(state.routes['notes'], ['draft'])
        for keys in [(), ('same', 'same'), ('valid', '')]:
            with self.assertRaises(ValueError):
                NavigationState(keys)
        with self.assertRaises(ValueError):
            state.select('home')

    def test_portable_namespace_and_state_import_without_any_toolkit(self):
        script = '''
import importlib.abc, sys
class Reject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'toga', 'PySide6', 'java', 'rubicon', 'logisticsmobile'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Reject())
import commonUtils.ui.native
from commonUtils.ui.native.navigation_state import NavigationState
assert NavigationState(('gallery',)).destination == 'gallery'
'''
        self.run_isolated(script)

    @unittest.skipUnless(importlib.util.find_spec('toga'), 'Optional Toga backend is not installed')
    def test_toga_consumer_uses_navigation_routes_and_canvas_without_logistics(self):
        script = '''
import importlib.abc, sys
class Reject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'logisticsmobile', 'features', 'PySide6'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Reject())
import toga
from commonUtils.ui.native.navigation import NativeNavigationHost
from commonUtils.ui.native.routes import Routes
from commonUtils.ui.native.image_canvas import ImageCanvas
from commonUtils.ui.native.password_input import PasswordInput
password = PasswordInput()
password.value = 'independent secret'
password.eye.on_press()
assert password.revealed and password.value == 'independent secret'
password.value = ''
assert not password.revealed
app = toga.App('Independent consumer', 'org.example.native-components')
host = NativeNavigationHost((('gallery', 'Gallery', 'photo', 'ic_menu_gallery'),
                             ('notes', 'Notes', 'doc', 'ic_menu_edit')))
routes = Routes(host, guard=lambda: True, changed=lambda panel: None)
draft = toga.MultilineTextInput(value='independent draft')
routes.show(draft, destination='notes', route='draft')
routes.show(toga.Label('Tools'), route='tools')
assert routes.back()
assert routes.body().children[0] is draft
assert draft.value == 'independent draft'
host.activate('gallery')
canvas = ImageCanvas()
assert canvas.page_axis == 'horizontal'
vertical = ImageCanvas(page_axis='vertical')
assert vertical.page_axis == 'vertical'
vertical.dispose()
try:
    ImageCanvas(page_axis='diagonal')
except ValueError:
    pass
else:
    raise AssertionError('Unsupported paging axis accepted')
canvas.fit_page()
assert canvas.zoom_scale == 1
canvas.dispose()
assert canvas.on_page is None and canvas.on_toggle is None
host.activate('notes')
assert routes.body().children[0] is draft
host.dispose()
from commonUtils.ui.native.editor_search import EditorSearch
from toga.style import Pack
from toga.style.pack import COLUMN
editor = toga.MultilineTextInput(value='😀 Cat cat')
container = toga.Box(children=[editor], style=Pack(direction=COLUMN))
search = EditorSearch(editor, container)
search.query.value = 'cat'
search.find()
assert search.span == (2, 5)
search.find()
assert search.span == (6, 9)
search.find()
assert search.span == (2, 5)
search.find(backwards=True)
assert search.span == (6, 9)
search.case.value = True
search.changed()
search.find()
assert search.span == (6, 9)
search.replacement.value = r'\1'
search.replace_all()
assert editor.value == '😀 Cat ' + r'\1'
search.toggle()
assert search.box in container.children
search.toggle()
assert search.box not in container.children
assert not any(name.startswith('logisticsmobile') for name in sys.modules)
'''
        self.run_isolated(script, dummy=True)

    def run_isolated(self, script, *, dummy=False):
        root = Path(__file__).resolve().parents[3]
        env = dict(os.environ, PYTHONPATH=str(root))
        if dummy:
            import toga
            # Keep the optional backend visible when supplied through a separate
            # existing environment; still import shared source from this checkout.
            dependencies = str(Path(toga.__file__).resolve().parent.parent)
            env['PYTHONPATH'] = os.pathsep.join((str(root), dependencies))
            env['TOGA_BACKEND'] = 'toga_dummy'
        result = subprocess.run([sys.executable, '-c', script], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
