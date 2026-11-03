"""Native slider tracks and thumbs with caller-supplied palette and direction."""
from ..readers.layout import READER_LAYOUT


def style_slider(slider, *, apple_color=None, palette=None, force_ltr=False, reverse_fill=False):
    backend = next((base.__module__ for base in type(slider._impl).__mro__
                    if base.__module__.startswith(('toga_iOS.', 'toga_android.'))), '')
    if backend.startswith('toga_iOS.'):
        if apple_color is None:
            from .appearance import default_apple_color
            apple_color = default_apple_color
        _apple(slider._impl.native, apple_color, force_ltr, reverse_fill)
    elif backend.startswith('toga_android.'):
        if palette is None:
            from .appearance import default_palette
            palette = default_palette
        _android(slider._impl.native, palette, force_ltr, reverse_fill)


def _apple(native, apple_color, force_ltr, reverse_fill=False):
    from rubicon.objc import ObjCClass, Block, objc_id, UIEdgeInsets
    from toga_iOS.libs import UIGraphicsImageRenderer, CGSize, CGRect

    def image(size, role, *, circle=False):
        # A bitmap freezes dynamic UIColor at draw time. Register both native
        # appearances so UIKit can select the correct artwork after trait changes.
        traits_class = ObjCClass('UITraitCollection')
        asset = ObjCClass('UIImageAsset').alloc().init()
        renderer = UIGraphicsImageRenderer.alloc().initWithSize(CGSize(size, size))
        for style in (1, 2):
            traits = traits_class.traitCollectionWithTraitsFromCollections([
                native.traitCollection, traits_class.traitCollectionWithUserInterfaceStyle(style)])
            def draw(context):
                apple_color(role).resolvedColorWithTraitCollection(traits).setFill()
                rect = CGRect((0, 0), (size, size))
                path = (ObjCClass('UIBezierPath').bezierPathWithOvalInRect(rect) if circle else
                        ObjCClass('UIBezierPath').bezierPathWithRoundedRect(rect, cornerRadius=size / 2))
                path.fill()
            rendered = renderer.imageWithActions(Block(draw, None, objc_id))
            if not circle:
                rendered = rendered.resizableImageWithCapInsets(UIEdgeInsets(0, 1, 0, 1), resizingMode=1)
            asset.registerImage(rendered, withTraitCollection=traits)
        return asset.imageWithTraitCollection(native.traitCollection)

    if force_ltr:
        native.semanticContentAttribute = 3
    native.setMinimumTrackImage(image(READER_LAYOUT.track_extent, 'border' if reverse_fill else 'accent'), forState=0)
    native.setMaximumTrackImage(image(READER_LAYOUT.track_extent, 'accent' if reverse_fill else 'border'), forState=0)
    native.setThumbImage(image(READER_LAYOUT.thumb_extent, 'accent', circle=True), forState=0)


def _android(native, palette, force_ltr, reverse_fill=False):
    from android import R
    from android.graphics import Color
    from android.graphics.drawable import GradientDrawable, LayerDrawable, ClipDrawable
    from android.view import Gravity
    density = native.getResources().getDisplayMetrics().density
    dark = native.getResources().getConfiguration().uiMode & 0x30 == 0x20
    colors = palette(dark)
    def dp(value):
        return round(value * density)
    def shape(role, *, circle=False):
        drawable = GradientDrawable()
        drawable.setColor(Color.parseColor(colors[role]))
        drawable.setShape(GradientDrawable.OVAL if circle else GradientDrawable.RECTANGLE)
        if circle:
            drawable.setSize(dp(READER_LAYOUT.thumb_extent), dp(READER_LAYOUT.thumb_extent))
        else:
            drawable.setCornerRadius(dp(READER_LAYOUT.track_extent / 2))
        return drawable
    track = LayerDrawable([shape('accent' if reverse_fill else 'border'),
                           ClipDrawable(shape('border' if reverse_fill else 'accent'), Gravity.LEFT, ClipDrawable.HORIZONTAL)])
    for index, identifier in enumerate((R.id.background, R.id.progress)):
        track.setId(index, identifier)
        track.setLayerHeight(index, dp(READER_LAYOUT.track_extent))
        track.setLayerGravity(index, Gravity.CENTER_VERTICAL)
    if force_ltr:
        native.setLayoutDirection(0)
    native.setProgressTintList(None)
    native.setProgressBackgroundTintList(None)
    native.setThumbTintList(None)
    native.setProgressDrawable(track)
    native.setThumb(shape('accent', circle=True))
    native.setThumbOffset(dp(READER_LAYOUT.thumb_extent / 2))
    native.setSplitTrack(False)
    native.setPadding(dp(READER_LAYOUT.thumb_extent / 2), 0, dp(READER_LAYOUT.thumb_extent / 2), 0)
