"""Native slider tracks and thumbs with caller-supplied palette and direction."""


def style_slider(slider, *, apple_color=None, palette=None, force_ltr=False):
    backend = type(slider._impl).__module__
    if backend.startswith('toga_iOS.'):
        if apple_color is None:
            from .appearance import default_apple_color
            apple_color = default_apple_color
        _apple(slider._impl.native, apple_color, force_ltr)
    elif backend.startswith('toga_android.'):
        if palette is None:
            from .appearance import default_palette
            palette = default_palette
        _android(slider._impl.native, palette, force_ltr)


def _apple(native, apple_color, force_ltr):
    from rubicon.objc import ObjCClass, Block, objc_id, UIEdgeInsets
    from toga_iOS.libs import UIGraphicsImageRenderer, CGSize, CGRect

    def image(size, role, *, circle=False):
        renderer = UIGraphicsImageRenderer.alloc().initWithSize(CGSize(size, size))
        def draw(context):
            apple_color(role).setFill()
            rect = CGRect((0, 0), (size, size))
            path = (ObjCClass('UIBezierPath').bezierPathWithOvalInRect(rect) if circle else
                    ObjCClass('UIBezierPath').bezierPathWithRoundedRect(rect, cornerRadius=size / 2))
            path.fill()
        return renderer.imageWithActions(Block(draw, None, objc_id))

    if force_ltr:
        native.semanticContentAttribute = 3
    native.setMinimumTrackImage(image(4, 'accent').resizableImageWithCapInsets(UIEdgeInsets(0, 1, 0, 1), resizingMode=1), forState=0)
    native.setMaximumTrackImage(image(4, 'border').resizableImageWithCapInsets(UIEdgeInsets(0, 1, 0, 1), resizingMode=1), forState=0)
    native.setThumbImage(image(16, 'accent', circle=True), forState=0)


def _android(native, palette, force_ltr):
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
            drawable.setSize(dp(16), dp(16))
        else:
            drawable.setCornerRadius(dp(2))
        return drawable
    track = LayerDrawable([shape('border'), ClipDrawable(shape('accent'), Gravity.LEFT, ClipDrawable.HORIZONTAL)])
    for index, identifier in enumerate((R.id.background, R.id.progress)):
        track.setId(index, identifier)
        track.setLayerHeight(index, dp(4))
        track.setLayerGravity(index, Gravity.CENTER_VERTICAL)
    if force_ltr:
        native.setLayoutDirection(0)
    native.setProgressTintList(None)
    native.setProgressBackgroundTintList(None)
    native.setThumbTintList(None)
    native.setProgressDrawable(track)
    native.setThumb(shape('accent', circle=True))
    native.setThumbOffset(dp(8))
    native.setSplitTrack(False)
    native.setPadding(dp(8), 0, dp(8), 0)
