"""Reader gestures restore native navigation state across controller changes."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from commonUtils.ui.native.chrome import NavigationChrome


class Gesture:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def isEnabled(self):
        return self.enabled

    def setEnabled(self, value):
        self.enabled = value


class Navigation:
    def __init__(self, *, content=True):
        self.interactivePopGestureRecognizer = Gesture()
        if content:
            self.interactiveContentPopGestureRecognizer = Gesture(False)

    def respondsToSelector(self, name):
        return hasattr(self, name)


class NativeReaderGestureTests(unittest.TestCase):
    def test_apple_target_normalizes_real_location_and_preserves_programmatic_toggle(self):
        from commonUtils.ui.native import image_canvas
        from unittest.mock import Mock
        class NativeBase:
            def __init_subclass__(cls, **kwargs):
                pass
        objc = SimpleNamespace(ObjCClass=lambda name: NativeBase, ObjCProtocol=lambda name: object(),
            objc_method=lambda method: method, objc_property=lambda *args, **kwargs: None, objc_id=object)
        with patch.dict(sys.modules, {'rubicon.objc': objc,
                'rubicon.objc.runtime': SimpleNamespace(send_super=Mock())}), \
                patch.object(image_canvas, '_scroll_class', None):
            target = image_canvas.apple_scroll_class()()
        picture = SimpleNamespace(bounds=SimpleNamespace(size=SimpleNamespace(width=200, height=400)))
        interface = SimpleNamespace(tap=Mock(), toggle_controls=Mock())
        target.owner = SimpleNamespace(picture=picture, interface=interface)
        gesture = SimpleNamespace(locationInView=lambda view: SimpleNamespace(x=50, y=300))
        target.toggleControls_(gesture)
        interface.tap.assert_called_once_with(.25, .75)
        interface.toggle_controls.assert_not_called()
        target.toggleControls_(None)
        interface.toggle_controls.assert_called_once_with()

    def test_image_tap_coordinates_consumption_and_letterbox_fallback(self):
        from commonUtils.ui.native.image_canvas import ImageCanvas
        from unittest.mock import Mock
        toggle, tap = Mock(), Mock(return_value=True)
        image = SimpleNamespace(image=object(), on_tap=tap, toggle_controls=toggle)
        ImageCanvas.tap(image, .2, .8)
        tap.assert_called_once_with(.2, .8)
        toggle.assert_not_called()
        tap.return_value = False
        ImageCanvas.tap(image, .3, .7)
        toggle.assert_called_once_with()
        tap.reset_mock()
        ImageCanvas.tap(image, -.1, .7)
        tap.assert_not_called()
        self.assertEqual(toggle.call_count, 2)

    def test_both_pop_gestures_disabled_and_original_states_restored(self):
        navigation = Navigation()
        host = SimpleNamespace(adapter=SimpleNamespace(navigation=[navigation], navigation_for=lambda destination: navigation),
                               destinations=['reader'], state=SimpleNamespace(destination='reader'))
        chrome = NavigationChrome(host)
        with patch.dict(sys.modules, {'rubicon.objc': SimpleNamespace(SEL=lambda value: value)}):
            chrome.set_page_swipes(True)
            chrome.set_page_swipes(True)
            self.assertFalse(navigation.interactivePopGestureRecognizer.enabled)
            self.assertFalse(navigation.interactiveContentPopGestureRecognizer.enabled)
            self.assertEqual(len(chrome.page_gestures), 2)
            chrome.set_page_swipes(False)
            self.assertTrue(navigation.interactivePopGestureRecognizer.enabled)
            self.assertFalse(navigation.interactiveContentPopGestureRecognizer.enabled)

    def test_split_controller_change_and_uninstall_restore_edge_only_older_system(self):
        primary, secondary = Navigation(content=False), Navigation()
        host = SimpleNamespace(adapter=SimpleNamespace(navigation=[primary], navigation_for=lambda destination: primary),
                               destinations=['reader'], state=SimpleNamespace(destination='reader'))
        chrome = NavigationChrome(host)
        with patch.dict(sys.modules, {'rubicon.objc': SimpleNamespace(SEL=lambda value: value)}):
            chrome.set_page_swipes(True)
            chrome.set_page_swipes(True, navigation=secondary)
            self.assertTrue(primary.interactivePopGestureRecognizer.enabled)
            self.assertFalse(secondary.interactivePopGestureRecognizer.enabled)
            chrome.restore()
            self.assertTrue(secondary.interactivePopGestureRecognizer.enabled)
            self.assertFalse(secondary.interactiveContentPopGestureRecognizer.enabled)

class AndroidImmersiveChromeTests(unittest.TestCase):
    def test_system_and_application_bars_restore_without_recapturing_hidden_state(self):
        from unittest.mock import Mock
        bar = Mock()
        bar.getVisibility.return_value = 0
        title = Mock()
        title.isShowing.return_value = True
        activity = Mock()
        activity.getSupportActionBar.return_value = title
        decor = activity.getWindow.return_value.getDecorView.return_value
        controller = Mock()
        controller.getSystemBarsBehavior.return_value = 1
        insets = Mock()
        insets.isVisible.side_effect = lambda kind: kind == 1
        compat = SimpleNamespace(getInsetsController=lambda window, view: controller)
        view_compat = SimpleNamespace(getRootWindowInsets=lambda view: insets, requestApplyInsets=Mock())
        types = SimpleNamespace(statusBars=lambda: 1, navigationBars=lambda: 2, systemBars=lambda: 7)
        classes = {'androidx.core.view.WindowCompat': compat, 'androidx.core.view.ViewCompat': view_compat,
                   'androidx.core.view.WindowInsetsCompat$Type': types,
                   'androidx.core.view.WindowInsetsControllerCompat': SimpleNamespace(BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE=2)}
        host = SimpleNamespace(adapter=SimpleNamespace(impl=SimpleNamespace(
            native_navigationview=bar, _native_activity=activity)), state=SimpleNamespace(destination='reader'))
        chrome = NavigationChrome(host)
        with patch.dict(sys.modules, {'java': SimpleNamespace(jclass=lambda name: classes[name])}):
            chrome.set_hidden(True)
            chrome.set_hidden(True)
            controller.hide.assert_called_with(7)
            self.assertEqual(insets.isVisible.call_count, 2)
            chrome.set_hidden(False)
        controller.show.assert_called_once_with(1)
        self.assertEqual(controller.hide.call_args.args, (2,))
        controller.setSystemBarsBehavior.assert_called_with(1)
        bar.setVisibility.assert_called_with(0)
        title.show.assert_called_once()
        self.assertFalse(chrome.restore_callbacks)


if __name__ == '__main__':
    unittest.main()
