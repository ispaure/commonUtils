"""Native transitions respect motion policy; slider painting uses supplied roles."""
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import unittest
from commonUtils.ui.native import transitions, sliders


def content(backend):
    impl = type('Impl', (), {'__module__': backend})()
    impl.native = Mock()
    return NS(_impl=impl)


class NativeReaderPresentationTests(unittest.TestCase):
    def test_direction_disabled_effects_and_system_reduced_motion(self):
        for rtl in (False, True):
            self.assertEqual(transitions.page_direction(None, 1, right_to_left=rtl), 0)
            self.assertEqual(transitions.page_direction(1, 1, right_to_left=rtl), 0)
            self.assertEqual(transitions.page_direction(1, 2, right_to_left=rtl), -1 if rtl else 1)
        widget = Mock()
        transitions.begin_page_slide(widget, 1, enabled=False)
        transitions.finish_page_slide(widget, 0)
        self.assertFalse(widget.mock_calls)
        widget = content('toga_iOS.widgets.box')
        reduced, animation = Mock(return_value=True), Mock()
        factory = Mock()
        factory.animation.return_value = animation
        with patch('ctypes.CDLL', return_value=NS(UIAccessibilityIsReduceMotionEnabled=reduced)), \
             patch.dict('sys.modules', {'rubicon.objc': NS(ObjCClass=lambda name: factory)}):
            transitions.begin_page_slide(widget, -1, duration=.35)
            widget._impl.native.layer.addAnimation.assert_not_called()
            reduced.return_value = False
            transitions.begin_page_slide(widget, -1, duration=.35)
        self.assertEqual(animation.duration, .35)
        self.assertEqual(animation.subtype, 'fromLeft')
        widget._impl.native.layer.addAnimation.assert_called_once()

    def test_android_animation_uses_pane_relative_motion_and_system_enablement(self):
        widget = content('toga_android.widgets.box')
        enabled, factory = Mock(return_value=0), Mock()
        modules = {
            'android.provider': NS(Settings=NS(Global=NS(ANIMATOR_DURATION_SCALE='scale', getFloat=enabled))),
            'android.view.animation': NS(TranslateAnimation=factory),
        }
        with patch.dict('sys.modules', modules):
            transitions.finish_page_slide(widget, 1, duration=.35)
            factory.assert_not_called()
            enabled.return_value = 1
            transitions.finish_page_slide(widget, -1, duration=.35)
        factory.assert_called_once_with(1, -1.0, 1, 0.0, 1, 0.0, 1, 0.0)
        factory.return_value.setDuration.assert_called_once_with(350)

    def test_android_slider_preserves_platform_direction_unless_requested(self):
        widget = content('toga_android.widgets.slider')
        native = widget._impl.native
        native.getResources.return_value.getDisplayMetrics.return_value.density = 2
        native.getResources.return_value.getConfiguration.return_value.uiMode = 0x20
        shapes = []
        def shape():
            value = Mock()
            shapes.append(value)
            return value
        gradient = Mock(side_effect=shape, OVAL=1, RECTANGLE=0)
        clip, layer = Mock(HORIZONTAL=1), Mock()
        palette = Mock(return_value={'accent': '#112233', 'border': '#aabbcc'})
        modules = {
            'android': NS(R=NS(id=NS(background=1, progress=2))),
            'android.graphics': NS(Color=NS(parseColor=lambda value: value)),
            'android.graphics.drawable': NS(GradientDrawable=gradient, ClipDrawable=clip, LayerDrawable=layer),
            'android.view': NS(Gravity=NS(LEFT=3, CENTER_VERTICAL=16)),
        }
        with patch.dict('sys.modules', modules):
            sliders.style_slider(widget, palette=palette)
            native.setLayoutDirection.assert_not_called()
            palette.assert_called_once_with(True)
            self.assertEqual(shapes[0].setColor.call_args.args, ('#aabbcc',))
            self.assertEqual(shapes[-1].setColor.call_args.args, ('#112233',))
            shapes[-1].setSize.assert_called_once_with(32, 32)
            native.setPadding.assert_called_with(16, 0, 16, 0)
            sliders.style_slider(widget, palette=palette, force_ltr=True)
            native.setLayoutDirection.assert_called_once_with(0)
            for reverse in (True, False):
                shapes.clear()
                sliders.style_slider(widget, palette=palette, force_ltr=True, reverse_fill=reverse)
                self.assertEqual(shapes[0].setColor.call_args.args,
                                 ('#112233' if reverse else '#aabbcc',))
                self.assertEqual(shapes[1].setColor.call_args.args,
                                 ('#aabbcc' if reverse else '#112233',))
                self.assertEqual(shapes[2].setColor.call_args.args, ('#112233',))

    def test_apple_reverse_fill_swaps_tracks_but_preserves_accent_thumb(self):
        widget = content('toga_iOS.widgets.slider')
        renderer = Mock()
        renderer.imageWithActions.side_effect = lambda draw: (draw(None), Mock())[1]
        renderer_class = Mock()
        renderer_class.alloc.return_value.initWithSize.return_value = renderer
        colors = Mock(return_value=Mock())
        modules = {
            'rubicon.objc': NS(ObjCClass=Mock(), Block=lambda draw, *args: draw,
                               objc_id=object, UIEdgeInsets=lambda *args: args),
            'toga_iOS.libs': NS(UIGraphicsImageRenderer=renderer_class,
                                CGSize=lambda *args: args, CGRect=lambda *args: args),
        }
        with patch.dict('sys.modules', modules):
            for reverse in (True, False):
                colors.reset_mock()
                sliders.style_slider(widget, apple_color=colors, force_ltr=True, reverse_fill=reverse)
                self.assertEqual([call.args[0] for call in colors.call_args_list],
                                 ['border', 'accent', 'accent'] if reverse else ['accent', 'border', 'accent'])
                self.assertEqual(widget._impl.native.semanticContentAttribute, 3)
