"""IME chrome lifetime: resizing, dismissal and independent reader ownership."""
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from commonUtils.ui.native.navigation import AndroidNavigation


class Rect:
    top = bottom = 0
    def height(self):
        return self.bottom - self.top


class KeyboardLayoutTests(unittest.TestCase):
    def adapter(self, *, height=300, visibility=0, title_showing=True):
        state = NS(keyboard=True, height=height, padding=0, visibility=visibility, showing=title_showing)
        bar = NS(getVisibility=lambda: state.visibility,
                 setVisibility=lambda value: setattr(state, 'visibility', value))
        title = NS(isShowing=lambda: state.showing, hide=lambda: setattr(state, 'showing', False),
                   show=lambda: setattr(state, 'showing', True))
        def visible(rect):
            rect.top, rect.bottom = 0, state.height
        native = NS(getWindowVisibleDisplayFrame=visible, getGlobalVisibleRect=visible,
                    getPaddingBottom=lambda: state.padding,
                    setPadding=lambda x, y, z, value: setattr(state, 'padding', value))
        adapter = AndroidNavigation.__new__(AndroidNavigation)
        adapter.keyboard_chrome = None
        adapter.host = NS(chrome=NS(context=None))
        adapter.impl = NS(native=native, native_navigationview=bar, scale_in=lambda value: value,
                           _native_activity=NS(getSupportActionBar=lambda: title))
        def jclass(name):
            if name.endswith('ViewCompat'):
                return NS(getRootWindowInsets=lambda native: NS(isVisible=lambda kind: state.keyboard))
            return NS(ime=lambda: 8)
        modules = {'android.graphics': NS(Rect=Rect), 'java': NS(jclass=jclass)}
        return adapter, state, modules

    def update(self, adapter, modules):
        with patch.dict(sys.modules, modules):
            adapter.update_keyboard_inset()

    def test_hides_once_and_stays_latched_through_resize_until_dismissal(self):
        adapter, state, modules = self.adapter()
        self.update(adapter, modules)
        self.assertEqual(state.visibility, 8)
        self.assertFalse(state.showing)
        saved = adapter.keyboard_chrome
        state.height = 450
        self.update(adapter, modules)
        self.assertIs(adapter.keyboard_chrome, saved)
        state.keyboard = False
        self.update(adapter, modules)
        self.assertEqual(state.visibility, 0)
        self.assertTrue(state.showing)
        self.assertIsNone(adapter.keyboard_chrome)

    def test_restores_original_hidden_bars_and_leaves_tall_windows_alone(self):
        adapter, state, modules = self.adapter(visibility=8, title_showing=False)
        self.update(adapter, modules)
        state.keyboard = False
        self.update(adapter, modules)
        self.assertEqual(state.visibility, 8)
        self.assertFalse(state.showing)
        state.height, state.keyboard = 600, True
        self.update(adapter, modules)
        self.assertIsNone(adapter.keyboard_chrome)

    def test_reader_context_takes_ownership(self):
        adapter, state, modules = self.adapter()
        self.update(adapter, modules)
        adapter.host.chrome.context = ('reader', None)
        self.update(adapter, modules)
        self.assertIsNone(adapter.keyboard_chrome)
        self.assertEqual(state.visibility, 0)
        self.assertTrue(state.showing)
        self.update(adapter, modules)
        self.assertIsNone(adapter.keyboard_chrome)

    def test_rotation_does_not_leave_cached_bottom_bar_hidden(self):
        adapter, state, modules = self.adapter()
        self.update(adapter, modules)
        rail = NS(visibility=0)
        rail.setVisibility = lambda value: setattr(rail, 'visibility', value)
        adapter.transfer_keyboard_chrome(rail)
        self.assertEqual(state.visibility, 0)
        self.assertEqual(rail.visibility, 8)
        state.keyboard = False
        self.update(adapter, modules)
        self.assertEqual(rail.visibility, 0)
        self.assertEqual(state.visibility, 0)
        self.assertTrue(state.showing)
