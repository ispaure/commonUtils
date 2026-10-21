"""Retained native toolbar mounting and centered titles; no route policy."""
_title_view_type = None


def centered_title_width(width, reference_width, *, group_left=None, clearance=24, minimum=44):
    """Only a same-row action group's explicit position constrains the title."""
    if group_left is None:
        return width
    return min(width, max(minimum, 2 * (group_left - reference_width / 2 - clearance)))


def apple_bar_group(buttons, *, native_control=lambda button: button._impl.native, size=44):
    """Constrain custom controls so Toga refresh cannot collapse their frames."""
    from rubicon.objc import ObjCClass, CGRect
    group = ObjCClass('UIStackView').alloc().initWithFrame(CGRect((0, 0), (size * len(buttons), size)))
    group.axis, group.distribution, group.alignment, group.spacing = 0, 1, 0, 0
    group.widthAnchor.constraintEqualToConstant(size * len(buttons)).active = True
    group.heightAnchor.constraintEqualToConstant(size).active = True
    item = ObjCClass('UIBarButtonItem').alloc().initWithCustomView(group)
    for button in buttons:
        native = native_control(button)
        native.translatesAutoresizingMaskIntoConstraints = False
        group.addArrangedSubview(native)
    return item, group


def apple_bar_separator(width=8):
    """A fixed space splits UIKit's shared glass, including on iOS 26+."""
    from rubicon.objc import ObjCClass
    item = ObjCClass('UIBarButtonItem').alloc().initWithBarButtonSystemItem(6, target=None, action=None)
    item.width = width
    return item


def apple_bar_title(text, width, actions, *, color=None, reference=None):
    """Keep the visible title centered even with asymmetric UIKit bar groups."""
    global _title_view_type
    from rubicon.objc import ObjCClass, objc_method, objc_property, send_super, CGRect
    if _title_view_type is None:
        class CommonUtilsCenteredBarTitle(ObjCClass('UIView')):
            readerActions = objc_property(object)
            readerWidth = objc_property(object)
            titleReference = objc_property(object)

            @objc_method
            def didMoveToWindow(self) -> None:
                send_super(__class__, self, 'didMoveToWindow')
                self.setNeedsLayout()

            @objc_method
            def layoutSubviews(self) -> None:
                send_super(__class__, self, 'layoutSubviews')
                label, window = self.viewWithTag(7311), self.titleReference or self.window
                window = window() if callable(window) else window
                if label is None or window is None:
                    return
                group = self.readerActions
                group_window = group.window if group is not None else None
                group_window = group_window() if callable(group_window) else group_window
                group_left = None
                if group_window is not None:
                    rect = group.convertRect(group.bounds, toView=window)
                    own = self.convertRect(self.bounds, toView=window)
                    if abs(float(rect.origin.y - own.origin.y)) < 44:
                        group_left = float(rect.origin.x)
                available = centered_title_width(float(self.bounds.size.width),
                    float(window.bounds.size.width), group_left=group_left)
                if self.readerWidth is None:
                    label.translatesAutoresizingMaskIntoConstraints = False
                    width_constraint = label.widthAnchor.constraintEqualToConstant(available)
                    self.readerWidth = width_constraint
                    label.centerXAnchor.constraintEqualToAnchor(window.centerXAnchor).active = True
                    label.centerYAnchor.constraintEqualToAnchor(self.centerYAnchor).active = True
                    label.heightAnchor.constraintEqualToAnchor(self.heightAnchor).active = True
                    width_constraint.active = True
                else:
                    self.readerWidth.constant = available
        _title_view_type = CommonUtilsCenteredBarTitle
    view = _title_view_type.alloc().initWithFrame(CGRect((0, 0), (width, 32)))
    view.readerActions = actions
    view.titleReference = reference
    view.readerWidth = None
    label = ObjCClass('UILabel').alloc().initWithFrame(view.bounds)
    label.tag = 7311
    label.text = label.accessibilityLabel = text
    label.font = ObjCClass('UIFont').systemFontOfSize(17, weight=.6)
    label.textAlignment, label.lineBreakMode = 1, 5
    from .appearance import default_apple_color
    label.textColor = color if color is not None else default_apple_color('text')
    view.addSubview(label)
    return view, label



def android_bar(context, leading, trailing, *, native_control=lambda button: button._impl.native):
    """Mount existing controls once, reserving symmetric space around title/status.

    The caller retains controls and owns detaching Toga parents and assigning
    window/app ownership through native_control before the native mount.
    """
    from android.view import Gravity, View
    from android.widget import FrameLayout, LinearLayout, TextView
    from android.text import TextUtils
    buttons = trailing
    root = FrameLayout(context)
    density = root.getResources().getDisplayMetrics().density
    size = round(48 * density)
    label = TextView(context)
    label.setSingleLine(True)
    label.setEllipsize(TextUtils.TruncateAt.MIDDLE)
    label.setGravity(Gravity.CENTER)
    label.setTextSize(17)
    status = TextView(context)
    status.setSingleLine(True)
    status.setEllipsize(TextUtils.TruncateAt.MIDDLE)
    status.setGravity(Gravity.CENTER)
    status.setTextSize(12)
    titles = LinearLayout(context)
    titles.setOrientation(1)
    titles.setGravity(Gravity.CENTER)
    titles.addView(label, LinearLayout.LayoutParams(-1, -2))
    titles.addView(status, LinearLayout.LayoutParams(-1, -2))
    params = FrameLayout.LayoutParams(-1, -1)
    params.leftMargin = params.rightMargin = max(len(leading), len(buttons)) * size
    root.addView(titles, params)
    for group, gravity in ((leading, Gravity.START), (buttons, Gravity.END)):
        native_group = LinearLayout(context)
        native_group.setGravity(Gravity.CENTER_VERTICAL)
        root.addView(native_group, FrameLayout.LayoutParams(-2, -1, gravity))
        for button in group:
            native = native_control(button)
            parent = native.getParent()
            if parent is not None:
                parent.removeView(native)
            native.setVisibility(View.VISIBLE)
            native_group.addView(native, LinearLayout.LayoutParams(size, -1))
    return root, label, status
