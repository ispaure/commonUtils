"""Small native presentation helpers; system colours follow light/dark appearance."""

def surface(widget):
    if type(widget._impl).__module__.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        native = widget._impl.native
        colour = ObjCClass('UIColor').secondarySystemGroupedBackgroundColor()
        widget._impl._default_background_color = colour
        native.backgroundColor = colour
        native.layer.cornerRadius = 10
    return widget


def list_button(button):
    from travertino.size import at_least
    # Text may truncate inside a row rather than widening the whole scroll view.
    button.intrinsic.width = at_least(44)
    backend = type(button._impl).__module__
    if backend.startswith(('toga_iOS.', 'toga_android.')) and not getattr(button._impl, '_row_hint', False):
        import weakref
        reference = weakref.ref(button)
        native_rehint = type(button._impl).rehint
        def rehint():
            target = reference()
            if target is not None:
                native_rehint(target._impl)
                target.intrinsic.width = at_least(44)
        button._impl.rehint = rehint
        button._impl._row_hint = True
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        native = button._impl.native
        native.contentHorizontalAlignment = 1
        native.titleLabel.lineBreakMode = 4
        native.tintColor = ObjCClass('UIColor').labelColor()
        native.setTitleColor(native.tintColor, forState=0)
        native.accessibilityLabel = button.text
    elif backend.startswith('toga_android.'):
        from android.text import TextUtils
        from android.content.res import ColorStateList
        from com.google.android.material import R as MaterialR
        button._impl._list_row = True
        native = button._impl.native
        native.setBackgroundTintList(ColorStateList.valueOf(button._impl.get_theme_color(MaterialR.attr.colorSurface)))
        native.setGravity(3 | 16)
        native.setSingleLine(True)
        native.setEllipsize(TextUtils.TruncateAt.END)
    return button


def hierarchy_row(label, *, depth=0, expanded=None, on_toggle=None, on_activate=None,
                  selected=False):
    """A navigation row with independent 48-unit disclosure and title targets.

    Hosts may style the returned row, ``disclosure`` and ``title_button``.
    ``expanded=None`` reserves a matching column for a leaf. Targets and tree
    state remain owned by the caller, so expanding never activates a page.
    """
    import toga
    from toga.style import Pack
    from toga.style.pack import ROW, CENTER
    row = toga.Box(style=Pack(direction=ROW, align_items=CENTER, margin_bottom=4))
    row.add(toga.Box(style=Pack(width=min(max(0, depth), 8) * 20)))
    row.disclosure = None
    if expanded is None:
        row.add(toga.Box(style=Pack(width=48, height=48)))
    else:
        disclosure = row.disclosure = navigation_button('forward',
            ('Collapse ' if expanded else 'Expand ') + label, on_press=on_toggle)
        backend = type(disclosure._impl).__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            disclosure.text = ''
            disclosure._impl.native.setImage(ObjCClass('UIImage').systemImageNamed(
                'chevron.down' if expanded else 'chevron.right'), forState=0)
        elif backend.startswith('toga_android.'):
            # Rotate the drawn chevron, keeping the full native touch target.
            disclosure._impl.native.setRotation(90 if expanded else 0)
        else:
            disclosure.text = '⌄' if expanded else '›'
        row.add(disclosure)
    button = row.title_button = list_button(toga.Button(label, on_press=on_activate,
        style=Pack(flex=1, height=48, font_size=15)))
    button.hierarchy_selected = selected
    row.add(button)
    return row


def template_icon(image):
    if type(image._impl).__module__.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        native = image._impl.native
        native.image = native.image.imageWithRenderingMode(2)
        native.tintColor = ObjCClass('UIColor').labelColor()
    return image


def scroll_content(view):
    """Give a reparented subtree a fresh root and zero layout origin.

    The pinned layout engine retains the old parent's origin on a detached
    subtree. A fresh Box rebases both ancestry and coordinates through public
    parenting APIs before the subtree becomes scroll content.
    """
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN
    return toga.Box(children=[view], style=Pack(direction=COLUMN))


def sidebar_button(callback, label='Browse folders'):
    """Accessible hamburger control with an Apple symbol and portable fallback."""
    import toga
    from toga.style import Pack
    button = toga.Button('☰', on_press=callback, style=Pack(width=48, height=48))
    button.accessible_name = label
    backend = type(button._impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        button.text = ''
        button._impl.native.setImage(ObjCClass('UIImage').systemImageNamed('line.3.horizontal'), forState=0)
        button._impl.native.accessibilityLabel = label
    elif backend.startswith('toga_android.'):
        button._impl.native.setContentDescription(label)
    return button


def navigation_button(direction, label, *, on_press=None, enabled=True):
    """48-point arrow control with native glyphs and an accessible action name."""
    import toga
    from toga.style import Pack
    symbols = {'find': ('magnifyingglass', '⌕', (((11, 3), (5, 5), (3, 11), (5, 16), (11, 18), (16, 16), (18, 11), (16, 5), (11, 3)), ((16, 16), (22, 22)))),
               'back': ('chevron.left', '‹', (((15, 5), (8, 12), (15, 19)),)),
               'forward': ('chevron.right', '›', (((9, 5), (16, 12), (9, 19)),)),
               'up': ('arrow.up', '↑', (((5, 11), (12, 4), (19, 11)), ((12, 4), (12, 21))))}
    from .icons import IconRenderer, IconSpec
    button = toga.Button(on_press=on_press, enabled=enabled, style=Pack(width=48, height=48))
    return IconRenderer({name: IconSpec(*artwork) for name, artwork in symbols.items()}).apply(button, direction, label)


class HierarchyList:
    """A flat preorder hierarchy with independent expand and activate targets."""
    def __init__(self, entries, choose, *, row_style=None, selected=None):
        import toga
        from toga.style import Pack
        from toga.style.pack import COLUMN
        self.entries, self.choose = list(entries), choose
        self.row_style, self.selected = row_style, selected
        self.collapsed = set()
        self.rows = toga.Box(style=Pack(direction=COLUMN))
        self.render()

    def render(self):
        self.rows.clear()
        hidden_depth = None
        for number, entry in enumerate(self.entries):
            if hidden_depth is not None and entry.depth > hidden_depth:
                continue
            hidden_depth = None
            nested = number + 1 < len(self.entries) and self.entries[number + 1].depth > entry.depth
            toggle = None
            if nested:
                def toggle(widget=None, number=number, **kwargs):
                    if number in self.collapsed:
                        self.collapsed.remove(number)
                    else:
                        self.collapsed.add(number)
                    self.render()
            def activate(widget=None, entry=entry, **kwargs):
                return self.choose(entry)
            selected = bool(self.selected and self.selected(entry))
            row = hierarchy_row(entry.label, depth=entry.depth,
                expanded=number not in self.collapsed if nested else None,
                on_toggle=toggle, on_activate=activate, selected=selected)
            row.title_button.hierarchy_entry = entry
            if self.row_style is not None:
                self.row_style(row, selected)
            self.rows.add(row)
            if nested and number in self.collapsed:
                hidden_depth = entry.depth
