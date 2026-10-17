"""Password entry with a native eye button and one in-memory value."""
import toga
from toga.style import Pack
from toga.style.pack import ROW


class PasswordInput(toga.Box):
    def __init__(self, *, placeholder='', on_confirm=None, style=None):
        self.field = toga.PasswordInput(placeholder=placeholder, on_confirm=on_confirm,
                                        on_change=self._changed,
                                        style=Pack(flex=1, height=48))
        self.revealed = False
        self.eye = toga.Button(on_press=self.toggle_visibility, style=Pack(width=48, height=48))
        self._update_eye()
        super().__init__(children=[self.field, self.eye], style=style)
        self.style.direction = ROW
        height = self.style.height
        self.style.height = max(height, 48) if isinstance(height, (int, float)) else 48

    def _changed(self, widget, **kwargs):
        if not widget.value and hasattr(self, 'eye'):
            self.set_revealed(False)

    def toggle_visibility(self, widget=None, **kwargs):
        if self.enabled:
            self.set_revealed(not self.revealed)

    def set_revealed(self, revealed):
        native = self.field._impl.native if hasattr(self.field._impl, 'native') else None
        backend = type(self.field._impl).__module__
        if backend.startswith('toga_iOS.'):
            value, selection = self.field.value, native.selectedTextRange
            native.setSecureTextEntry(not revealed)
            native.text = value
            if selection is not None:
                native.selectedTextRange = selection
        elif backend.startswith('toga_android.'):
            from android.text.method import PasswordTransformationMethod
            start, end = native.getSelectionStart(), native.getSelectionEnd()
            native.setTransformationMethod(None if revealed else PasswordTransformationMethod.getInstance())
            if start >= 0 and end >= 0:
                native.setSelection(start, end)
        self.revealed = revealed
        self._update_eye()

    def _update_eye(self):
        label = 'Hide password' if self.revealed else 'Show password'
        button = self.eye
        button.text = '◉̸' if self.revealed else '◉'
        button.accessible_name = label
        button.control_icon = 'eye_off' if self.revealed else 'eye'
        backend = type(button._impl).__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            button.text = ''
            native = button._impl.native
            symbol = 'eye.slash' if self.revealed else 'eye'
            native.setImage(ObjCClass('UIImage').systemImageNamed(symbol), forState=0)
            config = ObjCClass('UIImageSymbolConfiguration').configurationWithPointSize(22, weight=5)
            native.setPreferredSymbolConfiguration(config, forImageInState=0)
            native.accessibilityLabel = label
        elif backend.startswith('toga_android.'):
            from android.graphics import Path, Paint
            from android.graphics.drawable import ShapeDrawable
            from android.graphics.drawable.shapes import PathShape
            path = Path()
            path.moveTo(2, 12)
            path.cubicTo(7, 3, 17, 3, 22, 12)
            path.cubicTo(17, 21, 7, 21, 2, 12)
            path.addCircle(12, 12, 3, Path.Direction.CW)
            if self.revealed:
                path.moveTo(4, 3)
                path.lineTo(20, 21)
            drawable = ShapeDrawable(PathShape(path, 24, 24))
            paint = drawable.getPaint()
            paint.setStyle(Paint.Style.STROKE)
            paint.setStrokeWidth(1.8)
            paint.setStrokeCap(Paint.Cap.ROUND)
            paint.setAntiAlias(True)
            native = button._impl.native
            density = native.getResources().getDisplayMetrics().density
            size, padding = round(24 * density), round(12 * density)
            drawable.setBounds(0, 0, size, size)
            drawable.setTintList(native.getTextColors())
            button.text = ''
            native.setMinimumWidth(0)
            native.setMinimumHeight(0)
            native.setPadding(padding, padding, padding, padding)
            native.setCompoundDrawablesRelative(drawable, None, None, None)
            native.setContentDescription(label)
            button._impl._control_drawable = drawable

    @property
    def value(self):
        return self.field.value

    @value.setter
    def value(self, value):
        self.field.value = value
        if not self.field.value:
            self.set_revealed(False)

    @property
    def enabled(self):
        return self.field.enabled

    @enabled.setter
    def enabled(self, value):
        self.field.enabled = self.eye.enabled = value

    @property
    def on_confirm(self):
        return self.field.on_confirm

    @on_confirm.setter
    def on_confirm(self, handler):
        self.field.on_confirm = handler

    def focus(self):
        self.field.focus()
