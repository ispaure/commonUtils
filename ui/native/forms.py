"""Measured native form text, grouped surfaces and retained disclosures."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN


def wrap_text(text, width, measure):
    """Insert explicit line breaks: Toga labels do not wrap on iOS."""
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split():
            candidate = (line + ' ' + word).lstrip()
            if measure(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            if measure(word) <= width:
                line = word
                continue
            line = ''
            # Build identifiers must also fit the pane.
            for char in word:
                if line and measure(line + char) > width:
                    lines.append(line)
                    line = ''
                line += char
        lines.append(line)
    return '\n'.join(lines)


def fit_text(control, width, *, style_button=None):
    """Fit retained text to its pane using the actual native font on Apple."""
    control._settings_available_width = width
    previous = getattr(control, '_settings_rendered_text', None)
    current = control.text
    if current != previous:
        control._settings_source_text = current
    source = control._settings_source_text
    button = isinstance(control, toga.Button)
    width = max(24, width - (24 if button else 0)
                - (24 if getattr(control, '_settings_disclosure', False) else 0)
                - (32 if getattr(control, 'leading_icons', ()) else 0))
    size = control.style.font_size
    if size is None or size <= 0:
        size = 17
    line_height = size * 1.4
    # A retained page's text and font normally stay unchanged. Avoid even native
    # font/line-height reads on repeat navigation through the Python UI bridge.
    measure_key = (source, width, size, control.style.font_family, control.style.font_weight)
    if getattr(control, '_settings_measure_key', None) == measure_key and current == previous:
        return
    def measure(text):
        return len(text) * size * .65
    if type(control._impl).__module__.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass, CGSize
        native = control._impl.native
        font = native.titleLabel.font if button else native.font
        line_height = float(font.lineHeight)
    key = (source, width, line_height)
    if getattr(control, '_settings_fit_key', None) == key and current == previous:
        return
    if type(control._impl).__module__.startswith('toga_iOS.'):
        ruler = getattr(control, '_settings_ruler', None)
        if ruler is None:
            ruler = control._settings_ruler = ObjCClass('UILabel').new()
        ruler.font = font
        def measure(text):
            ruler.text = text
            return float(ruler.sizeThatFits(CGSize(100000, 100000)).width)
    control._settings_fit_key = key
    control._settings_measure_key = measure_key
    rendered = wrap_text(source, width, measure)
    if rendered != control.text:
        # Toga's public Button setter discards everything after a newline.
        # Apply presentation text without replacing a SettingsLabel's source.
        control._impl.set_text(rendered)
        control.refresh()
    control._settings_rendered_text = rendered
    if button:
        if style_button is not None and not getattr(control, '_settings_list_styled', False):
            style_button(control)
            control._settings_list_styled = True
        control.style.height = max(52 if getattr(control, '_settings_row', False) else 48, int(line_height * len(rendered.split('\n')) + 20))
        if type(control._impl).__module__.startswith('toga_iOS.'):
            control._impl.native.titleLabel.numberOfLines = len(rendered.split('\n'))
            control._impl.native.accessibilityLabel = source
        elif type(control._impl).__module__.startswith('toga_android.'):
            control._impl.native.setSingleLine(False)
            control._impl.native.setMaxLines(len(rendered.split('\n')))


def fit_section(section, width, *, fit=fit_text, reserved_width=None):
    """Keep each category within its scroll viewport, including switch rows."""
    width = max(24, width - section.style.margin_left - section.style.margin_right)
    reserve = reserved_width(section) if reserved_width is not None else None
    if reserve is not None:
        fit(section.children[0], max(24, width - reserve))
        return
    for child in section.children:
        if isinstance(child, (toga.Label, toga.Button)):
            fit(child, max(24, width - child.style.margin_left - child.style.margin_right))
        elif isinstance(child, toga.Box):
            fit_section(child, width, fit=fit, reserved_width=reserved_width)


def disclosure(button, *, apple_color=None):
    """A trailing accessory inside the native button's full accessible hit target."""
    button._settings_disclosure = True
    backend = type(button._impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass, UIEdgeInsets
        native = button._impl.native
        # The accessory is an overlaid subview, unlike Android's end drawable.
        # Reserve its width and a gap in the title's actual layout as well as
        # the text-fitting estimate, including after a theme repaint.
        button._impl._content_trailing_inset = 32
        native.contentEdgeInsets = UIEdgeInsets(0, native.contentEdgeInsets.left, 0, 32)
        image = ObjCClass('UIImage').systemImageNamed('chevron.right')
        accessory = ObjCClass('UIImageView').alloc().initWithImage(image)
        accessory.translatesAutoresizingMaskIntoConstraints = False
        from .appearance import default_apple_color
        accessory.tintColor = (apple_color or default_apple_color)('muted')
        accessory.isAccessibilityElement = False
        native.addSubview(accessory)
        accessory.trailingAnchor.constraintEqualToAnchor(native.trailingAnchor, constant=-8).active = True
        accessory.centerYAnchor.constraintEqualToAnchor(native.centerYAnchor).active = True
        accessory.widthAnchor.constraintEqualToConstant(10).active = True
        accessory.heightAnchor.constraintEqualToConstant(16).active = True
    elif backend.startswith('toga_android.'):
        from .icons import IconSpec, android_drawable
        arrow = android_drawable(IconSpec('', '', (((8, 5), (15, 12), (8, 19)),)))
        native = button._impl.native
        size = button._impl.scale_in(24)
        arrow.setBounds(0, 0, size, size)
        # State-aware tint follows the title, including Android E Ink selection.
        arrow.setTintList(native.getTextColors())
        button._impl._settings_accessory = arrow
        native.setCompoundDrawablesRelative(getattr(button._impl, '_control_drawable', None), None, arrow, None)
    return button


def group_rows(rows, *, surface, icon_inset=False, background='surface', separator='separator'):
    """One shared surface with inset separators, never a box per preference."""
    group = surface(toga.Box(style=Pack(direction=COLUMN, margin_bottom=20)),
                    radius=16, background=background, outlined=False)
    group._settings_group = True
    for index, row in enumerate(rows):
        if index:
            group.add(surface(toga.Box(style=Pack(height=1, margin_left=48 if icon_inset else 16,
                                                 margin_right=16)), radius=0,
                              background=separator, outlined=False, eink_outlined=False))
        # Nested layout boxes and native pickers must share the card fill.
        if isinstance(row, (toga.Box, toga.Selection)):
            surface(row, radius=0, background='transparent', outlined=False, eink_outlined=False)
        row.style.margin_left = 12
        row.style.margin_right = 12
        row.style.margin_top = 4 if index == 0 else 0
        row.style.margin_bottom = 4 if index == len(rows) - 1 else 0
        group.add(row)
    return group


class FittedLabel(toga.Label):
    """Refit asynchronous status messages as soon as their text changes."""
    @toga.Label.text.setter
    def text(self, value):
        toga.Label.text.fset(self, value)
        width = getattr(self, '_settings_available_width', None)
        if width is not None:
            fit_text(self, width)


def collapsible(title, children, *, style_button=lambda button: button, changed=None):
    """Keep child controls and values alive while collapsed; notify after toggles."""
    body = toga.Box(children=children, style=Pack(direction=COLUMN))
    box = toga.Box(style=Pack(direction=COLUMN))
    def toggle(widget=None, **kwargs):
        if body.parent is None:
            box.add(body)
            button.text = title + ' −'
        else:
            box.remove(body)
            button.text = title + ' +'
        if changed is not None:
            changed(box)
    button = style_button(toga.Button(title + ' +', on_press=toggle, style=Pack(height=48)))
    box.add(button)
    return box, button
