"""Native template icons from consumer-supplied immutable artwork."""
from dataclasses import dataclass
from functools import lru_cache
import weakref
from .appearance import accessible_name


@dataclass(frozen=True)
class IconSpec:
    symbol: str
    fallback: str
    lines: tuple = ()
    circles: tuple = ()
    arcs: tuple = ()
    fills: tuple = ()
    stroke_width: float = 1.8
    apple_stroke_width: float | None = None
    filled: bool = False
    text: str | None = None
    apple_vector: bool = False


def android_path(lines=(), *, circles=(), arcs=(), fills=False):
    from android.graphics import Path
    path = Path()
    if fills:
        path.setFillType(Path.FillType.EVEN_ODD)
    for line in lines:
        if not line:
            continue
        path.moveTo(*line[0])
        for point in line[1:]:
            path.lineTo(*point)
        if fills:
            path.close()
    for x, y, radius in circles:
        path.addCircle(x, y, radius, Path.Direction.CW)
    for arc in arcs:
        path.addArc(*arc)
    return path


def android_drawable(spec, *, width=24, height=24, bounds=None, resources=None):
    """Return a fresh mutable drawable; never share tint or bounds across controls."""
    from android.graphics import Paint
    from android.graphics.drawable import ShapeDrawable
    from android.graphics.drawable.shapes import PathShape
    path = android_path(spec.lines, circles=spec.circles, arcs=spec.arcs)
    drawable = ShapeDrawable(PathShape(path, width, height))
    paint = drawable.getPaint()
    paint.setStyle(Paint.Style.FILL if spec.filled else Paint.Style.STROKE)
    paint.setStrokeWidth(spec.stroke_width)
    paint.setStrokeCap(Paint.Cap.ROUND)
    paint.setStrokeJoin(Paint.Join.ROUND)
    paint.setAntiAlias(True)
    if bounds is not None:
        drawable.setBounds(0, 0, *bounds)
    if spec.text is not None or spec.fills:
        if bounds is None or resources is None:
            raise ValueError('Raster artwork requires bounds and resources')
        from android.graphics import Bitmap, Canvas
        from android.graphics.drawable import BitmapDrawable
        bitmap = Bitmap.createBitmap(*bounds, Bitmap.Config.ARGB_8888)
        canvas = Canvas(bitmap)
        canvas.scale(bounds[0] / width, bounds[1] / height)
        canvas.drawPath(path, paint)
        paint.setStyle(Paint.Style.FILL)
        if spec.fills:
            canvas.drawPath(android_path(spec.fills, fills=True), paint)
        if spec.text is not None:
            paint.setTextSize(10)
            paint.setTextAlign(Paint.Align.CENTER)
            canvas.drawText(spec.text, width / 2, height / 2 + .5 - (paint.ascent() + paint.descent()) / 2, paint)
        drawable = BitmapDrawable(resources, bitmap)
        drawable.setBounds(0, 0, *bounds)
    return drawable


@lru_cache(maxsize=64)
def apple_symbols(symbols, scale):
    """Cache immutable template pixels, leaving tint/state with each button."""
    from rubicon.objc import ObjCClass, Block, objc_id
    from toga_iOS.libs import UIGraphicsImageRenderer, CGSize, CGRect
    width = 28 * len(symbols) - 4
    image_format = ObjCClass('UIGraphicsImageRendererFormat').defaultFormat()
    image_format.scale = scale
    renderer = UIGraphicsImageRenderer.alloc().initWithSize(CGSize(width + 8, 24), format=image_format)
    configuration = ObjCClass('UIImageSymbolConfiguration').configurationWithPointSize(22, weight=5)
    images = [ObjCClass('UIImage').systemImageNamed(symbol).imageWithConfiguration(configuration) for symbol in symbols]
    def draw(context):
        for index, image in enumerate(images):
            ratio = min(24 / float(image.size.width), 24 / float(image.size.height))
            w, h = float(image.size.width) * ratio, float(image.size.height) * ratio
            image.drawInRect(CGRect((28 * index + (24 - w) / 2, (24 - h) / 2), (w, h)))
    return renderer.imageWithActions(Block(draw, None, objc_id)).imageWithRenderingMode(2)


def apple_vector(spec):
    from math import radians
    from rubicon.objc import ObjCClass, Block, objc_id, ns_from_py
    from toga_iOS.libs import UIGraphicsImageRenderer, CGSize, CGPoint, CGRect
    renderer = UIGraphicsImageRenderer.alloc().initWithSize(CGSize(24, 24))
    def draw(context):
        color = ObjCClass('UIColor').blackColor
        color = color() if callable(color) else color
        color.setStroke()
        color.setFill()
        path = ObjCClass('UIBezierPath').bezierPath()
        path.lineWidth = spec.apple_stroke_width or spec.stroke_width
        path.lineCapStyle = path.lineJoinStyle = 1
        for left, top, right, bottom, start, sweep in spec.arcs:
            path.addArcWithCenter(CGPoint((left + right) / 2, (top + bottom) / 2), radius=(right - left) / 2,
                                  startAngle=radians(start), endAngle=radians(start + sweep), clockwise=sweep > 0)
        for line in spec.lines:
            path.moveToPoint(CGPoint(*line[0]))
            for point in line[1:]:
                path.addLineToPoint(CGPoint(*point))
        if spec.filled:
            path.fill()
        else:
            path.stroke()
        if spec.fills:
            fill = ObjCClass('UIBezierPath').bezierPath()
            fill.usesEvenOddFillRule = True
            for contour in spec.fills:
                fill.moveToPoint(CGPoint(*contour[0]))
                for point in contour[1:]:
                    fill.addLineToPoint(CGPoint(*point))
                fill.closePath()
            fill.fill()
        if spec.text is not None:
            paragraph = ObjCClass('NSMutableParagraphStyle').alloc().init()
            paragraph.alignment = 1
            font = ObjCClass('UIFont').systemFontOfSize(10)
            ObjCClass('NSString').stringWithString(spec.text).drawInRect(
                CGRect((3, (25 - float(font.lineHeight)) / 2), (18, float(font.lineHeight))),
                withAttributes=ns_from_py({'NSFont': font, 'NSColor': color, 'NSParagraphStyle': paragraph}))
    return renderer.imageWithActions(Block(draw, None, objc_id)).imageWithRenderingMode(2)


class IconRenderer:
    """Retain consumer artwork and an optional Android tint callback."""
    def __init__(self, icons, *, tint_android=None):
        self.icons = dict(icons)
        self.tint_android = tint_android
        self.android_controls = weakref.WeakSet()

    def _android(self, button, drawable):
        button._impl._control_drawable = drawable
        self.android_controls.add(button._impl)
        if self.tint_android is None:
            drawable.setTintList(button._impl.native.getTextColors())
        else:
            self.tint_android(button._impl)

    def refresh(self):
        if self.tint_android is not None:
            for impl in list(self.android_controls):
                self.tint_android(impl)

    def leading(self, button, icons):
        icons = tuple(icons)
        button.leading_icons = icons
        if not icons:
            return button
        button._impl._content_inset = 12
        backend = type(button._impl).__module__
        width = 28 * len(icons) - 4
        labels = ' · '.join(label for _, label in icons)
        native = getattr(button._impl, 'native', None)
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, UIEdgeInsets
            image = apple_symbols(tuple(self.icons[name].symbol for name, _ in icons), float(ObjCClass('UIScreen').mainScreen.scale))
            native.setImage(image, forState=0)
            native.contentEdgeInsets = UIEdgeInsets(0, button._impl._content_inset, 0,
                getattr(button._impl, '_content_trailing_inset', button._impl._content_inset))
            native.accessibilityHint = ' · '.join(filter(None, (getattr(button, 'description', ''), labels)))
        elif backend.startswith('toga_android.'):
            lines = tuple(tuple((x + 28 * index, y) for x, y in line)
                          for index, (name, _) in enumerate(icons) for line in self.icons[name].lines)
            density = native.getResources().getDisplayMetrics().density
            drawable = android_drawable(IconSpec('', '', lines), width=width,
                bounds=(round(width * density), round(24 * density)))
            inset = button._impl.scale_in(button._impl._content_inset)
            native.setPaddingRelative(inset, native.getPaddingTop(), inset, native.getPaddingBottom())
            native.setCompoundDrawablesRelative(drawable, None, None, None)
            native.setCompoundDrawablePadding(round(8 * density))
            native.setContentDescription(' · '.join(filter(None,
                (button.text.partition('\n')[0], getattr(button, 'description', ''), labels))))
            self._android(button, drawable)
        return button

    def apply(self, button, name, label, *, preserve_layout=False, size=None):
        spec = self.icons[name]
        backend = type(button._impl).__module__
        if not preserve_layout:
            button.text = spec.fallback
            button.style.width = button.style.height = 48
        elif not backend.startswith(('toga_iOS.', 'toga_android.')):
            button.text = spec.fallback
        button.control_icon = name
        accessible_name(button, label)
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            if not preserve_layout:
                button.text = ''
            image = apple_vector(spec) if spec.apple_vector else ObjCClass('UIImage').systemImageNamed(spec.symbol)
            config = ObjCClass('UIImageSymbolConfiguration').configurationWithPointSize(size or 22, weight=4 if size else 5)
            button._impl.native.setImage(image, forState=0)
            if not preserve_layout:
                button._impl.native.setPreferredSymbolConfiguration(config, forImageInState=0)
        elif backend.startswith('toga_android.'):
            native = button._impl.native
            density = native.getResources().getDisplayMetrics().density
            icon_size = size or 24
            extent, padding = round(icon_size * density), round((48 - icon_size) / 2 * density)
            if preserve_layout and hasattr(button._impl, '_control_drawable'):
                extent = button._impl._control_drawable.getBounds().width()
            drawable = android_drawable(spec, bounds=(extent, extent), resources=native.getResources())
            if not preserve_layout:
                button.text = ''
                native.setMinimumWidth(0)
                native.setMinimumHeight(0)
                native.setPadding(padding, padding, padding, padding)
            native.setCompoundDrawablesRelative(drawable, None, None, None)
            self._android(button, drawable)
        return button
