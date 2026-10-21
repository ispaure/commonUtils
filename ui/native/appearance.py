"""Native surface painting with explicit palette, geometry and host callbacks."""
import sys
import weakref
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from ..appearance.colors import argb

_android_backgrounds = OrderedDict()


def default_palette(dark=False):
    return dict(text='#eeeeee' if dark else '#202020', muted='#aaaaaa' if dark else '#606060',
                surface='#202020' if dark else '#ffffff', hover='#404040' if dark else '#e8e8e8',
                accent='#80b0ff' if dark else '#2060d0', border='#606060' if dark else '#cccccc')


def default_apple_color(role):
    from rubicon.objc import ObjCClass
    names = dict(text='labelColor', muted='secondaryLabelColor', surface='secondarySystemBackgroundColor',
                 hover='tertiarySystemFillColor', accent='systemBlueColor', border='separatorColor',
                 transparent='clearColor')
    color = getattr(ObjCClass('UIColor'), names[role])
    return color() if callable(color) else color



@dataclass(frozen=True)
class SurfaceStyle:
    radius: float = 12
    background: str = 'surface'
    foreground: object = None
    outlined: bool = False
    border: str = 'border'
    high_contrast_outlined: bool = True
    high_contrast_selected: bool = False
    content_inset: float = 0
    trailing_inset: object = None
    glass: bool = False
    accessory: object = None


class DynamicAppleColors:
    """Retain dynamic UIKit providers for an explicit light/dark role mapping."""
    def __init__(self, palette):
        self.palette = palette
        self.colors = {}
        self.blocks = []

    def color(self, role):
        if role == 'transparent':
            from rubicon.objc import ObjCClass
            return ObjCClass('UIColor').clearColor
        if role not in self.colors:
            from rubicon.objc import ObjCClass, ObjCInstance, Block, objc_id
            colour = ObjCClass('UIColor')
            def resolve(traits):
                values = self.palette(ObjCInstance(traits).userInterfaceStyle == 2)
                value = int(values[role][1:], 16)
                return colour.colorWithRed(((value >> 16) & 255) / 255,
                    green=((value >> 8) & 255) / 255, blue=(value & 255) / 255, alpha=1).ptr.value
            block = Block(resolve, objc_id, objc_id)
            self.blocks.append(block)
            self.colors[role] = colour.colorWithDynamicProvider(block)
        return self.colors[role]


@lru_cache(maxsize=4)
def _android_surface_types(modules):
    # The module identities also isolate test/runtime module replacements.
    from android import R
    from android.content.res import ColorStateList
    from android.graphics.drawable import GradientDrawable, RippleDrawable
    return R, ColorStateList, GradientDrawable, RippleDrawable


@lru_cache(maxsize=128)
def _android_color_states(cls, enabled_attribute, disabled, enabled):
    # ColorStateList is immutable; drawable instances must remain independent.
    return cls([[-enabled_attribute], []], [disabled, enabled])


def _android_surface_resources():
    return _android_surface_types(tuple(id(sys.modules.get(name)) for name in
        ('android', 'android.content.res', 'android.graphics.drawable')))


def _android_background(types, *, background, radius, stroke, border, hover, button):
    _, colors, gradient, ripple = types
    key = (gradient, ripple, colors, background, radius, stroke, border, hover, button)
    state = _android_backgrounds.get(key)
    if state is None:
        drawable = gradient()
        drawable.setColor(background)
        drawable.setCornerRadius(radius)
        if stroke:
            drawable.setStroke(stroke, border)
        if button:
            drawable = ripple(colors.valueOf(hover), drawable, None)
        constant_state = getattr(drawable, 'getConstantState', None)
        state = constant_state() if constant_state is not None else None
        if state is None:
            return drawable
        _android_backgrounds[key] = state
        if len(_android_backgrounds) > 128:
            _android_backgrounds.popitem(last=False)
    else:
        _android_backgrounds.move_to_end(key)
    # Never share mutable bounds, tint, pressed or animation state across views.
    # Geometry is already expressed in device pixels; do not rescale it again.
    return state.newDrawable().mutate()


def accessible_name(widget, name):
    """Name icon-only controls without changing their visible title."""
    widget.accessible_name = name
    backend = type(widget._impl).__module__
    if backend.startswith('toga_iOS.'):
        widget._impl.native.accessibilityLabel = name
    elif backend.startswith('toga_android.'):
        widget._impl.native.setContentDescription(name)
    return widget


def set_android_background(native, drawable):
    """A colour/outline repaint must not replace the control's content insets.

    Android drawables can supply their own padding (including an empty Rect),
    which View.setBackground otherwise copies over the current layout.
    """
    padding = (native.getPaddingLeft(), native.getPaddingTop(),
               native.getPaddingRight(), native.getPaddingBottom())
    native.setBackground(drawable)
    native.setPadding(*padding)



def android_color_states(disabled, enabled):
    """Return an immutable native enabled/disabled foreground tint."""
    R, colors, _, _ = _android_surface_resources()
    return _android_color_states(colors, R.attr.state_enabled, disabled, enabled)


def clear_surface_caches():
    """Retire cached templates when replacing a native backend or test fixture."""
    _android_backgrounds.clear()
    _android_surface_types.cache_clear()
    _android_color_states.cache_clear()


class SurfacePainter:
    def __init__(self, *, palette=default_palette, apple_color=default_apple_color,
                 high_contrast=lambda: False, prepare_button=None, after_paint=None):
        self.palette, self.apple_color, self.high_contrast = palette, apple_color, high_contrast
        self.prepare_button, self.after_paint = prepare_button, after_paint
        self.pending = ContextVar('pending_surface_styles', default=None)

    @contextmanager
    def batch(self):
        if self.pending.get() is not None:
            yield
            return
        pending = weakref.WeakKeyDictionary()
        token = self.pending.set(pending)
        try:
            yield
        finally:
            self.pending.reset(token)
            for impl, style in list(pending.items()):
                self.paint(impl, style)

    def paint(self, impl, style):
        pending = self.pending.get()
        if pending is not None:
            pending[impl] = style
            return
        backend = type(impl).__module__
        background, foreground, outlined = style.background, style.foreground, style.outlined
        border, radius = style.border, style.radius
        apple_color = self.apple_color
        if backend.startswith('toga_iOS.'):
            native = impl.native
            impl._default_background_color = apple_color(background)
            native.backgroundColor = impl._default_background_color
            native.layer.cornerRadius = radius
            native.layer.borderWidth = 1 if outlined else 0
            native.layer.borderColor = apple_color(border).resolvedColorWithTraitCollection(native.traitCollection).CGColor
            if hasattr(impl.interface, 'on_press'):
                from rubicon.objc import UIEdgeInsets
                inset = style.content_inset
                native.contentEdgeInsets = UIEdgeInsets(0, inset, 0, style.trailing_inset if style.trailing_inset is not None else inset)
            if foreground:
                if hasattr(impl.interface, 'on_press'):
                    native.configuration = None
                    if style.glass:
                        from rubicon.objc import ObjCClass, SEL
                        configuration = ObjCClass('UIButtonConfiguration')
                        config = (configuration.glassButtonConfiguration()
                                  if configuration.respondsToSelector(SEL('glassButtonConfiguration'))
                                  else configuration.grayButtonConfiguration())
                        config.cornerStyle = 4
                        native.configuration = config
                    native.tintColor = apple_color(foreground)
                    native.setTitleColor(apple_color(foreground), forState=0)
                    native.setTitleColor(apple_color('muted'), forState=2)
                elif hasattr(impl.interface, 'image'):
                    native.tintColor = apple_color(foreground)
                else:
                    native.textColor = apple_color(foreground)
        elif backend.startswith('toga_android.'):
            types = _android_surface_resources()
            R, ColorStateList, _, _ = types
            resources = impl.native.getResources()
            colors = self.palette(resources.getConfiguration().uiMode & 0x30 == 0x20)
            eink = self.high_contrast()
            if eink and style.high_contrast_selected:
                colors = dict(colors, surface='#000000', alternate='#000000', hover='#000000',
                              text='#ffffff', muted='#ffffff')
            button = hasattr(impl.interface, 'on_press')
            if button and eink and self.prepare_button is not None:
                self.prepare_button(impl)
            has_outline = style.high_contrast_outlined if eink else outlined
            drawable = _android_background(types,
                background=0 if background == 'transparent' else argb(colors.get(background, colors['surface'])),
                radius=impl.scale_in(radius),
                stroke=max(1, impl.scale_in(1)) if has_outline else 0,
                border=argb(colors[border]), hover=argb(colors['hover']), button=button)
            if foreground:
                tint = _android_color_states(ColorStateList, R.attr.state_enabled,
                                            argb(colors['muted']), argb(colors.get(foreground, colors['text'])))
                accessory = style.accessory
                if accessory is not None:
                    accessory.setTintList(tint)
                if hasattr(impl.interface, 'image'):
                    impl.native.setImageTintList(tint)
                else:
                    impl.native.setTextColor(tint)
            if button:
                impl.native.setBackgroundTintList(None)
                impl.native.setStateListAnimator(None)
                impl.native.setElevation(0)
            set_android_background(impl.native, drawable)
            if self.after_paint is not None:
                self.after_paint(impl)
