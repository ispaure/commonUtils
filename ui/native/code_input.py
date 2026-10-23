"""Native source input with logical line numbers and shared Pygments colouring.

Keeps Toga's text control, keyboard, IME, selection and undo. Hosts retain files,
recovery and save policy. No document bytes enter a WebView or a disk cache.
"""
import asyncio
import toga
from ...formats.code_language import LanguageSelection
from ...formats.code_spans import line_offsets, syntax_spans

_apple_class = None
_gutter_class = None


def apple_value(owner, name):
    value = getattr(owner, name)
    return value() if callable(value) else value


def apple_view_class():
    global _apple_class
    if _apple_class is None:
        from toga_iOS.widgets.multilinetextinput import TogaMultilineTextView
        from rubicon.objc import objc_method, send_super, objc_id, CGRect

        class CommonUtilsCodeTextView(TogaMultilineTextView):
            @objc_method
            def traitCollectionDidChange_(self, previous: objc_id) -> None:
                send_super(__class__, self, 'traitCollectionDidChange:', previous, argtypes=[objc_id])
                if self.interface is not None:
                    self.interface.changed(notify=False)

            @objc_method
            def layoutSubviews(self) -> None:
                send_super(__class__, self, 'layoutSubviews')
                impl = self.impl
                gutter = getattr(impl, 'gutter', None)
                if gutter is not None:
                    bounds = self.bounds
                    geometry = (float(bounds.origin.x), float(bounds.origin.y),
                                float(self.textContainerInset.left - 4), float(bounds.size.height))
                    if geometry != getattr(impl, 'gutter_geometry', None):
                        impl.gutter_geometry = geometry
                        gutter.frame = CGRect(geometry[:2], geometry[2:])
                    self.bringSubviewToFront(gutter)
                    gutter.setNeedsDisplay()

        _apple_class = CommonUtilsCodeTextView
    return _apple_class



def apple_gutter_class():
    global _gutter_class
    if _gutter_class is None:
        from rubicon.objc import ObjCClass, objc_property, objc_method, CGRect, CGPoint
        class CommonUtilsCodeGutter(ObjCClass('UIView')):
            owner = objc_property(object, weak=True)
            @objc_method
            def drawRect_(self, rect: CGRect) -> None:
                try:
                    draw_apple_numbers(self)
                except Exception as error:
                    if self.owner is not None:
                        self.owner.gutter_error = str(error)

        _gutter_class = CommonUtilsCodeGutter
    return _gutter_class


def draw_apple_numbers(self):
    from rubicon.objc import ObjCClass, CGRect, CGPoint
    interface = self.owner
    if interface is None or not hasattr(interface, 'line_starts'):
        return
    native = interface._impl.native
    font = ObjCClass('UIFont').monospacedSystemFontOfSize(float(native.font.pointSize) * .85, weight=0)
    colour = apple_value(ObjCClass('UIColor'), 'secondaryLabelColor')
    attributes = {'NSFont': font, 'NSColor': colour}
    inset, bounds, manager = native.textContainerInset, native.bounds, native.layoutManager
    top, bottom = float(bounds.origin.y), float(bounds.origin.y + bounds.size.height)
    manager.ensureLayoutForTextContainer(native.textContainer)
    length = int(native.textStorage.length())
    def line_y(number):
        offset = interface.line_starts[number]
        if offset < length:
            glyph = manager.glyphIndexForCharacterAtIndex(offset)
            line = manager.lineFragmentRectForGlyphAtIndex(glyph, effectiveRange=None)
            return float(line.origin.y + inset.top)
        line = manager.extraLineFragmentRect
        return float(line.origin.y + inset.top) if line.size.height else float(inset.top)
    # Find the first visible logical row using actual fragment geometry.
    # glyphRangeForBoundingRect can omit rows after UITextView's caret scroll.
    low, high = 0, len(interface.line_starts)
    while low < high:
        middle = (low + high) // 2
        if line_y(middle) + float(native.font.lineHeight) < top:
            low = middle + 1
        else:
            high = middle
    for number in range(low, len(interface.line_starts)):
        y = line_y(number)
        if y > bottom:
            break
        if y + float(native.font.lineHeight) >= top:
            label = ObjCClass('NSString').stringWithString(str(number + 1))
            size = label.sizeWithAttributes(attributes)
            label.drawAtPoint(CGPoint(inset.left - size.width - 10, y - top), withAttributes=attributes)

def apple_backend(interface):
    from toga_iOS.widgets.multilinetextinput import MultilineTextInput
    from toga_iOS.libs import UILabel
    from rubicon.objc import ObjCClass, UIEdgeInsets

    class Backend(MultilineTextInput):
        def create(self):
            self.native = apple_view_class().alloc().init()
            self.native.interface, self.native.impl = self.interface, self
            self.native.delegate = self.native
            self.native.textContainerInset = UIEdgeInsets(8, 48, 8, 8)
            self.native.contentInsetAdjustmentBehavior = 2
            self.native.autocorrectionType = 1  # no correction
            self.native.autocapitalizationType = 0
            self.native.smartQuotesType = self.native.smartDashesType = 1
            self.placeholder_label = UILabel.alloc().init()
            self.placeholder_label.translatesAutoresizingMaskIntoConstraints = False
            self.placeholder_label.font = self.native.font
            self.placeholder_label.alpha = .5
            self.native.addSubview(self.placeholder_label)
            self.native.placeholder_label = self.placeholder_label
            self.constrain_placeholder_label()
            self.add_constraints()
            self.gutter = apple_gutter_class().alloc().init()
            self.gutter.owner = self.interface
            self.gutter.userInteractionEnabled = False
            self.gutter.opaque = False
            self.gutter.backgroundColor = apple_value(ObjCClass('UIColor'), 'clearColor')
            self.native.addSubview(self.gutter)

        def set_font(self, font):
            super().set_font(font)
            self.native.font = ObjCClass('UIFont').monospacedSystemFontOfSize(float(self.native.font.pointSize), weight=0)
            self.native.setNeedsDisplay()

    return Backend(interface=interface)


class CodeInput(toga.MultilineTextInput):
    """Drop-in multiline input; call set_filename on rename and dispose on close."""
    def __init__(self, *args, loop, filename='', on_change=None, highlighting=True, **kwargs):
        self.loop, self.filename = loop, filename
        self.changed_callback = on_change
        self.highlighting = highlighting
        self.language_selection = LanguageSelection()
        self.language = 'text'
        self.line_starts = [0]
        self.pending = self.worker = None
        self.closed = self.applying = False
        self.android_support = None
        super().__init__(*args, on_change=self.changed, **kwargs)
        self.style.font_family = 'monospace'
        backend = type(self._impl).__module__
        if backend.startswith('toga_android.'):
            from java import jclass
            readonly = self.readonly
            self.android_support = jclass('io.github.ispaure.commonutils.CodeEditorSupport')(self._impl.native)
            self.readonly = readonly
        self.changed()

    def _create(self):
        self.backend_name = self.factory.MultilineTextInput.__module__
        if self.backend_name.startswith('toga_android.'):
            # Include room for a line and EditText's native vertical padding,
            # without forcing Toga's 100-point minimum into a short IME pane.
            self._MIN_HEIGHT = 48
        if self.backend_name.startswith('toga_iOS.'):
            return apple_backend(self)
        return super()._create()

    @property
    def language_override(self):
        return self.language_selection.selected_id

    @language_override.setter
    def language_override(self, language):
        self.language_selection.select(language)

    def set_filename(self, filename):
        self.filename = filename
        self.changed(notify=False)

    def set_language(self, language=None):
        self.language_override = language
        self.changed(notify=False)

    def changed(self, widget=None, *, notify=True, **kwargs):
        if self.closed or self.applying or getattr(self, '_impl', None) is None:
            return
        self.line_starts = line_offsets(self.value)
        self.language_selection.update(self.filename, self.value)
        self.language = self.language_selection.language_id
        if hasattr(self._impl, 'native') and type(self._impl).__module__ == __name__:
            native = self._impl.native
            from rubicon.objc import UIEdgeInsets
            inset = native.textContainerInset
            font_size = float(native.font.pointSize) if native.font is not None else 16
            width = max(48, len(str(len(self.line_starts))) * font_size * .6 + 20)
            if abs(inset.left - width) > .5:
                native.textContainerInset = UIEdgeInsets(inset.top, width, inset.bottom, inset.right)
            self._impl.native.setNeedsLayout()
        if self.pending is not None:
            self.pending.cancel()
        self.pending = self.loop.call_later(.2, self.start_highlight)
        if notify and self.changed_callback is not None:
            self.changed_callback(self)

    def composing(self):
        if self.android_support is not None:
            return bool(self.android_support.isComposing())
        if type(self._impl).__module__ == __name__:
            return self._impl.native.markedTextRange is not None
        return False

    def start_highlight(self):
        self.pending = None
        if self.closed:
            return
        if self.composing() or (self.worker is not None and not self.worker.done()):
            self.pending = self.loop.call_later(.2, self.start_highlight)
            return
        self.worker = self.loop.create_task(self.highlight())

    async def highlight(self):
        text, filename = self.value, self.filename
        configuration = self.language, self.highlighting
        support = self.android_support
        apple = type(self._impl).__module__ == __name__
        dark = bool(support.isDark()) if support is not None else bool(apple and self._impl.native.traitCollection.userInterfaceStyle == 2)
        language = self.language if self.highlighting else 'text'
        _, spans = await asyncio.to_thread(syntax_spans, text, filename, language=language, dark=dark)
        if (self.closed or self.value != text or self.filename != filename or self.composing()
                or configuration != (self.language, self.highlighting)):
            return
        self.applying = True
        try:
            if support is not None:
                from java import jarray, jint
                support.syntax(*(jarray(jint)([span[column] for span in spans]) for column in range(3)))
            elif apple:
                from rubicon.objc import ObjCClass, NSRange
                native = self._impl.native
                storage = native.textStorage
                selection, offset = native.selectedRange, native.contentOffset
                storage.beginEditing()
                try:
                    storage.addAttribute('NSColor', value=apple_value(ObjCClass('UIColor'), 'labelColor'),
                                         range=NSRange(0, storage.length()))
                    for start, end, rgb in spans:
                        colour = ObjCClass('UIColor').colorWithRed((rgb >> 16 & 255) / 255,
                            green=(rgb >> 8 & 255) / 255, blue=(rgb & 255) / 255, alpha=1)
                        storage.addAttribute('NSColor', value=colour, range=NSRange(start, end - start))
                finally:
                    storage.endEditing()
                native.selectedRange = selection
                native.setContentOffset(offset, animated=False)
        finally:
            self.applying = False

    def dispose(self):
        self.closed = True
        self.changed_callback = None
        for task in (self.pending, self.worker):
            if task is not None:
                task.cancel()
        self.pending = self.worker = None
        if self.android_support is not None:
            self.android_support.dispose()
            self.android_support = None
