"""IME chrome lifetime: resizing, dismissal and independent reader ownership."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import sys
import importlib.util
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
if importlib.util.find_spec('toga'):
    from commonUtils.ui.native.navigation import AndroidNavigation
else:
    AndroidNavigation = None


class Rect:
    top = bottom = 0
    def height(self):
        return self.bottom - self.top


@unittest.skipUnless(AndroidNavigation is not None, 'Optional Toga backend is not installed')
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


@unittest.skipUnless(AndroidNavigation is not None, 'Optional Toga backend is not installed')
class AppleKeyboardLayoutTests(unittest.TestCase):
    def adapter(self, *, modern=True, hidden=False):
        from commonUtils.ui.native.navigation import AppleNavigation
        state = NS(hidden=hidden, key=True, insets=NS(bottom=0), scene=NS(activationState=0))
        class View:
            bounds = NS(size=NS(width=400, height=800))
            def setNeedsLayout(self): pass
            def layoutIfNeeded(self): pass
            def convertRect(self, rect, **kwargs): return rect
            @property
            def safeAreaInsets(self): return NS(bottom=34 + state.insets.bottom)
        view = View()
        class Parent:
            view = None
            @property
            def additionalSafeAreaInsets(self): return state.insets
            @additionalSafeAreaInsets.setter
            def additionalSafeAreaInsets(self, value): state.insets = value
        parent = Parent(); parent.view = view
        tab = NS(isHidden=lambda: state.hidden, setHidden=lambda value: setattr(state, 'hidden', value))
        controller = NS(tabBar=tab, view=view, respondsToSelector=lambda name: modern,
                        isTabBarHidden=lambda: state.hidden,
                        setTabBarHidden=lambda value, **kwargs: setattr(state, 'hidden', value))
        adapter = AppleNavigation.__new__(AppleNavigation)
        adapter.controller, adapter.parent = controller, parent
        adapter.window = NS(_impl=NS(native=NS(isKeyWindow=lambda: state.key,
            windowScene=state.scene,
            screen=NS(coordinateSpace=object()), convertRect=lambda rect, **kwargs: rect)))
        state.queued, state.resizes = [], 0
        adapter.window.app = NS(loop=NS(call_soon=state.queued.append))
        adapter.window.on_resize = lambda: setattr(state, 'resizes', state.resizes + 1)
        adapter.host = NS(chrome=NS(context=None))
        adapter.old_additional_insets = NS(bottom=0)
        adapter.keyboard_inset = 0
        adapter.keyboard_visible = False
        adapter.keyboard_tab_visibility = None
        adapter.keyboard_layout_pending = False
        adapter.keyboard_live = True
        adapter.keyboard_frame = None
        return adapter, state

    def test_ipad_sidebar_and_toggle_restore_original_presentation_after_nested_hiding(self):
        for sidebar_hidden in (True, False):
            adapter, state = self.adapter()
            adapter.sidebar_used = True
            state.sidebar_hidden = sidebar_hidden
            adapter.controller.mode = 2
            adapter.controller.setMode = lambda value: setattr(adapter.controller, 'mode', value)
            adapter.controller.sidebar = NS(isHidden=lambda: state.sidebar_hidden,
                setHidden=lambda value: setattr(state, 'sidebar_hidden', value))
            adapter.set_keyboard_tabs_hidden(True, True)
            self.assertEqual(adapter.controller.mode, 1)
            self.assertTrue(state.sidebar_hidden)
            adapter.set_keyboard_tabs_hidden(True, True)
            adapter.set_keyboard_tabs_hidden(True, False)
            self.assertEqual(adapter.controller.mode, 2)
            self.assertEqual(state.sidebar_hidden, sidebar_hidden)
            self.assertFalse(state.hidden)

    def test_inactive_scene_releases_keyboard_even_when_its_window_remains_key(self):
        adapter, state = self.adapter()
        self.frame(adapter)
        self.assertEqual(adapter.keyboard_inset, 266)
        state.scene.activationState = 1
        with patch.dict(sys.modules, {'rubicon.objc': NS(SEL=lambda value: value)}):
            adapter.refresh_keyboard_focus()
            self.assertFalse(adapter.keyboard_visible)
            self.assertEqual(adapter.keyboard_inset, 0)
            self.assertFalse(state.hidden)
            adapter.window._impl.native.windowScene = None
            adapter.refresh_keyboard_focus()
            self.assertFalse(adapter.keyboard_visible)
            adapter.window._impl.native.windowScene = state.scene
            state.scene.activationState = 0
            adapter.refresh_keyboard_focus()
        self.assertTrue(adapter.keyboard_visible)
        self.assertEqual(adapter.keyboard_inset, 266)

    def test_focus_notifications_ignore_other_scenes_and_retired_adapters(self):
        adapter, state = self.adapter()
        with patch.dict(sys.modules, {'rubicon.objc': NS(ObjCInstance=lambda value: value)}):
            adapter.keyboard_focus_changed(NS(object=object()))
            self.assertEqual(state.queued, [])
            adapter.keyboard_focus_changed(NS(object=state.scene))
            self.assertEqual(state.queued, [adapter.refresh_keyboard_focus])
        adapter.keyboard_live = False
        adapter.keyboard_focus_changed(object())
        adapter.refresh_keyboard_focus()

    def test_focus_reconciliation_keeps_the_original_screen_frame(self):
        from unittest.mock import Mock
        adapter, state = self.adapter()
        convert = Mock(side_effect=lambda frame, **kwargs: NS(
            origin=NS(x=frame.origin.x, y=frame.origin.y - 100), size=frame.size))
        adapter.window._impl.native.convertRect = convert
        self.frame(adapter)
        raw = adapter.keyboard_frame
        self.assertEqual(raw.origin.y, 500)
        convert.reset_mock()
        with patch.dict(sys.modules, {'rubicon.objc': NS(SEL=lambda value: value)}):
            adapter.refresh_keyboard_focus()
            adapter.refresh_keyboard_focus()
        self.assertEqual(convert.call_count, 2)
        for call in convert.call_args_list:
            self.assertIs(call.args[0], raw)
        self.assertEqual(raw.origin.y, 500)

    def frame(self, adapter, *, top=500, height=300, width=400):
        frame = NS(origin=NS(x=0, y=top), size=NS(width=width, height=height))
        notice = NS(userInfo=NS(objectForKey=lambda name: NS(CGRectValue=frame)))
        with patch.dict(sys.modules, {'rubicon.objc': NS(ObjCInstance=lambda value: value, SEL=lambda value: value)}):
            adapter.refresh_keyboard(notice)

    def test_keyboard_reclaims_tabs_and_dismissal_restores_original_visibility(self):
        for modern in (True, False):
            for hidden in (True, False):
                with self.subTest(modern=modern, hidden=hidden):
                    adapter, state = self.adapter(modern=modern, hidden=hidden)
                    self.frame(adapter)
                    self.assertTrue(state.hidden)
                    self.assertEqual(adapter.keyboard_inset, 266)
                    saved = adapter.keyboard_tab_visibility
                    self.frame(adapter)
                    self.assertEqual(adapter.keyboard_tab_visibility, saved)
                    self.assertEqual(adapter.keyboard_inset, 266)
                    self.frame(adapter, top=800)
                    self.assertEqual(state.hidden, hidden)
                    self.assertEqual(adapter.keyboard_inset, 0)
                    self.assertIsNone(adapter.keyboard_tab_visibility)

    def test_floating_keyboard_hides_tabs_without_full_width_inset(self):
        adapter, state = self.adapter()
        self.frame(adapter, top=300, height=200, width=200)
        self.assertTrue(state.hidden)
        self.assertEqual(adapter.keyboard_inset, 0)

    def test_other_window_and_disposed_observer_do_not_hide_tabs(self):
        adapter, state = self.adapter()
        state.key = False
        self.frame(adapter)
        self.assertFalse(state.hidden)
        self.assertEqual(adapter.keyboard_inset, 0)
        state.key, adapter.keyboard_live = True, False
        self.frame(adapter)
        self.assertFalse(state.hidden)

    def test_reader_snapshot_is_independent_and_keyboard_suppression_resumes(self):
        from commonUtils.ui.native.chrome import NavigationChrome
        adapter, state = self.adapter()
        host = NS(adapter=adapter)
        host.chrome = adapter.host.chrome = NavigationChrome(host)
        self.frame(adapter)
        adapter.restore_keyboard_chrome()
        self.assertFalse(state.hidden)
        host.chrome.context = ('reader', None)
        host.chrome.restore_callbacks.append(lambda: setattr(state, 'hidden', False))
        state.hidden = True
        self.frame(adapter)
        self.assertTrue(state.hidden)
        self.assertIsNone(adapter.keyboard_tab_visibility)
        with patch.dict(sys.modules, {'rubicon.objc': NS(SEL=lambda value: value)}):
            host.chrome.restore()
        self.assertTrue(state.hidden)
        self.frame(adapter, top=800)
        self.assertFalse(state.hidden)

    def test_resize_is_coalesced_and_retired_with_the_adapter(self):
        adapter, state = self.adapter()
        self.frame(adapter)
        self.frame(adapter)
        self.assertEqual(len(state.queued), 1)
        state.queued.pop()()
        self.assertEqual(state.resizes, 1)
        self.frame(adapter, top=800)
        self.assertEqual(len(state.queued), 1)
        adapter.keyboard_live = False
        state.queued.pop()()
        self.assertEqual(state.resizes, 1)
