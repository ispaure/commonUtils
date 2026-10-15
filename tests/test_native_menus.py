"""Menu callbacks stay host-owned; disposal blocks stale native selections."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from commonUtils.ui.native.menus import NativeMenu


class NativeMenuTests(unittest.TestCase):
    def test_fallback_and_disposal(self):
        button = SimpleNamespace(_impl=SimpleNamespace())
        calls = []
        menu = NativeMenu(button, [('Run', lambda: calls.append('run'))],
                          invoke=lambda callback: callback(), context=lambda: None,
                          fallback=lambda: calls.append('fallback'))
        menu.show()
        menu.invoke(menu.actions[0][1])
        menu.dispose()
        menu.dispose()
        menu.invoke(lambda: calls.append('stale'))
        menu.show()
        self.assertEqual(calls, ['fallback', 'run'])
        self.assertIsNone(button.on_press)

    def test_android_dispatch_and_stale_listener(self):
        class Popup:
            OnMenuItemClickListener = object
            def __init__(self, context, button): self.rows = []
            def getMenu(self): return self
            def add(self, group, identity, order, title): self.rows.append((identity, title))
            def setOnMenuItemClickListener(self, listener): self.listener = listener
            def show(self): pass
            def dismiss(self): self.dismissed = True
        impl = type('Impl', (), {'__module__': 'toga_android.widgets.button', 'native': object()})()
        button = SimpleNamespace(_impl=impl)
        calls = []
        menu = NativeMenu(button, [('A', lambda: calls.append('A')), ('B', lambda: calls.append('B'))],
                          invoke=lambda callback: callback(), context=lambda: object(), fallback=lambda: None)
        modules = {'android.widget': SimpleNamespace(PopupMenu=Popup),
                   'java': SimpleNamespace(dynamic_proxy=lambda interface: object)}
        with patch.dict('sys.modules', modules): menu.show()
        self.assertEqual(menu.popup.rows, [(0, 'A'), (1, 'B')])
        listener, popup = menu.listener, menu.popup
        listener.onMenuItemClick(SimpleNamespace(getItemId=lambda: 1))
        menu.dispose()
        listener.onMenuItemClick(SimpleNamespace(getItemId=lambda: 0))
        self.assertEqual(calls, ['B'])
        self.assertTrue(popup.dismissed)
        self.assertIsNone(popup.listener)
