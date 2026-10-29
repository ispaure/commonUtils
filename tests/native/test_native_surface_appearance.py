"""Surface batching and drawable isolation without an application palette."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch
from commonUtils.ui.native import appearance
from commonUtils.ui.appearance.colors import argb, contrast_ratio, readable_accent


class NativeSurfaceTests(TestCase):
    def test_default_apple_colors_accept_property_and_method_bridges(self):
        token = object()
        for color in (token, lambda: token):
            with patch.dict('sys.modules', {'rubicon.objc': NS(ObjCClass=lambda name: NS(tertiarySystemFillColor=color))}):
                self.assertIs(appearance.default_apple_color('hover'), token)

    def test_background_replacement_preserves_asymmetric_content_padding(self):
        class Native:
            padding = (12, 6, 32, 8)
            def getPaddingLeft(self): return self.padding[0]
            def getPaddingTop(self): return self.padding[1]
            def getPaddingRight(self): return self.padding[2]
            def getPaddingBottom(self): return self.padding[3]
            def setBackground(self, drawable):
                # Android applies drawable-supplied padding on replacement.
                self.padding = (0, 0, 0, 0)
            def setPadding(self, *padding): self.padding = padding
        native = Native()
        for _ in range(3):
            appearance.set_android_background(native, object())
            self.assertEqual(native.padding, (12, 6, 32, 8))


    def test_nested_offscreen_style_batch_applies_only_final_roles(self):
        class Impl:
            __module__ = 'toga_android.widgets.button'
        class Colors:
            def __new__(cls, states, colors):
                return NS(states=states, colors=colors)
        impl = Impl()
        impl.native = MagicMock()
        impl.native.getResources().getConfiguration().uiMode = 0x10
        impl.scale_in = lambda value: value
        button = NS(_impl=impl, on_press=lambda: None)
        impl.interface = button
        colors = dict(text='#202020', muted='#606060', surface='#ffffff', hover='#eeeeee', border='#cccccc')
        painter = appearance.SurfacePainter(palette=lambda dark: colors)
        with patch.object(appearance, '_android_surface_resources', return_value=(
                NS(attr=NS(state_enabled=1)), Colors, None, None)), patch.object(
                appearance, '_android_background', return_value=object()) as background:
            with painter.batch():
                painter.paint(impl, appearance.SurfaceStyle(radius=8, foreground='muted'))
                with painter.batch():
                    painter.paint(impl, appearance.SurfaceStyle(radius=4, background='alternate'))
                painter.paint(impl, appearance.SurfaceStyle(radius=0, background='transparent', foreground='text'))
                background.assert_not_called()
            self.assertEqual(background.call_count, 1)
            self.assertEqual(background.call_args.kwargs['background'], 0)
            self.assertEqual(background.call_args.kwargs['radius'], 0)
            self.assertEqual(impl.native.setBackground.call_count, 1)
            tint = impl.native.setTextColor.call_args.args[0]
            self.assertEqual(tint.colors, [argb(colors['muted']),
                                           argb(colors['text'])])


    def test_cached_background_templates_never_share_mutable_drawables(self):
        created = []
        class State:
            def __init__(self, values):
                self.values = values
            def newDrawable(self):
                clone = object.__new__(Gradient)
                clone.values = deepcopy(self.values)
                return clone
        class Gradient:
            def __init__(self):
                self.values = {}
                created.append(self)
            def setColor(self, value):
                self.values['color'] = value
            def setCornerRadius(self, value):
                self.values['radius'] = value
            def setStroke(self, width, color):
                self.values['stroke'] = width, color
            def getConstantState(self):
                return State(deepcopy(self.values))
            def mutate(self):
                return self
        types = (None, object, Gradient, object)
        args = dict(background=1, radius=8, stroke=1, border=2, hover=3, button=False)
        first = appearance._android_background(types, **args)
        second = appearance._android_background(types, **args)
        self.assertEqual(len(created), 1)
        self.assertIsNot(first, second)
        first.setColor(99)
        self.assertEqual(second.values, {'color': 1, 'radius': 8, 'stroke': (1, 2)})
        changed = appearance._android_background(types, **dict(args, background=4, radius=16))
        self.assertEqual(len(created), 2)
        self.assertEqual(changed.values['color'], 4)
        self.assertEqual(changed.values['radius'], 16)

    def test_dynamic_apple_roles_keep_provider_alive_and_follow_current_palette(self):
        colour = MagicMock()
        colour.clearColor = object()
        colour.colorWithDynamicProvider.side_effect = lambda provider: NS(provider=provider)
        colour.colorWithRed.side_effect = lambda red, **v: NS(ptr=NS(value=(red, v['green'], v['blue'], v['alpha'])))
        values = [dict(text='#000000'), dict(text='#ffffff')]
        palette = appearance.DynamicAppleColors(lambda dark: values[int(dark)])
        bridge = NS(ObjCClass=lambda name: colour, ObjCInstance=lambda value: value,
                    Block=lambda callback, *args: callback, objc_id=object)
        with patch.dict('sys.modules', {'rubicon.objc': bridge}):
            dynamic = palette.color('text')
            self.assertIs(palette.color('text'), dynamic)
            self.assertEqual(len(palette.blocks), 1)
            self.assertEqual(dynamic.provider(NS(userInterfaceStyle=1)), (0, 0, 0, 1))
            self.assertEqual(dynamic.provider(NS(userInterfaceStyle=2)), (1, 1, 1, 1))
            self.assertIs(palette.color('transparent'), colour.clearColor)
        colour.colorWithDynamicProvider.assert_called_once()

    def test_accessibility_labels_leave_visible_titles_unchanged(self):
        for backend in ('toga_iOS.widgets.button', 'toga_android.widgets.button'):
            impl = type('Impl', (), {'__module__': backend})()
            impl.native = MagicMock()
            widget = NS(_impl=impl, text='Visible')
            appearance.accessible_name(widget, 'Open document')
            self.assertEqual(widget.text, 'Visible')
            if backend.startswith('toga_iOS.'):
                self.assertEqual(impl.native.accessibilityLabel, 'Open document')
            else:
                impl.native.setContentDescription.assert_called_once_with('Open document')

    def test_argb_and_contrast_blending_preserve_signed_android_values(self):
        self.assertEqual(argb('#ffffff'), -1)
        self.assertEqual(argb('#000000'), -16777216)
        self.assertEqual(contrast_ratio(argb('#000000'), argb('#ffffff')), 21)
        self.assertEqual(contrast_ratio(argb('#ffffff'), argb('#ffffff')), 1)
        value = readable_accent(argb('#aaaaaa'), argb('#000000'), argb('#ffffff'))
        self.assertGreaterEqual(contrast_ratio(value, argb('#ffffff')), 4.5)
