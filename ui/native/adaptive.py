"""Reusable sidebar/detail presentation based on allocated logical width."""
from dataclasses import dataclass

@dataclass(frozen=True)
class SidebarPolicy:
    sidebar_width: float = 260
    detail_minimum: float = 448
    gap: float = 12

    def fits(self, available_width):
        return available_width >= self.sidebar_width + self.detail_minimum + self.gap


def allocated_width(widget, fallback):
    """Measure the parent allocation, capped by the host width, in points/dp.

    Parent bounds avoid using a child's content-driven minimum as available space.
    The host provides the current window/pane width before native layout exists.
    """
    parent = widget.parent
    if parent is None:
        return max(0, float(fallback))
    impl = parent._impl
    backend = type(impl).__module__
    width = 0
    if backend.startswith('toga_iOS.'):
        width = float(impl.native.bounds.size.width)
    elif backend.startswith('toga_android.'):
        native = impl.native
        density = native.getContext().getResources().getDisplayMetrics().density
        width = float(native.getWidth()) / density
    return min(float(fallback), width) if width > 0 else max(0, float(fallback))


class AdaptiveSidebar:
    """One retained sidebar/detail pair; narrow views use a hamburger toggle.

    Mount `view`, place `menu_button` in the host toolbar, and call `reflow` with
    usable content width on resize. This component does not inspect device names,
    physical screen size, resolution, or navigation routes.
    """
    def __init__(self, sidebar, detail, *, width=390, policy=None, label='Browse folders'):
        import toga
        from toga.style import Pack
        from toga.style.pack import ROW
        from .presentation import sidebar_button

        self.sidebar, self.detail = sidebar, detail
        self.policy = policy or SidebarPolicy()
        self.expanded = None
        self.sidebar_open = False
        self.view = toga.Box(style=Pack(direction=ROW, flex=1))
        self.menu_button = sidebar_button(self.toggle, label)
        self.reflow(width)

    def reflow(self, width):
        expanded = self.policy.fits(max(0, float(width)))
        if expanded == self.expanded:
            return False
        self.expanded = expanded
        self.render()
        return True

    def toggle(self, widget=None, **kwargs):
        if not self.expanded:
            self.sidebar_open = not self.sidebar_open
            self.render()

    def show_sidebar(self):
        self.sidebar_open = True
        self.render()

    def show_detail(self):
        self.sidebar_open = False
        self.render()

    def render(self):
        expected = ([self.sidebar, self.detail] if self.expanded else
                    [self.sidebar] if self.sidebar_open else [self.detail])
        self.sidebar.style.flex = 0 if self.expanded else 1
        if self.expanded:
            self.sidebar.style.width = self.policy.sidebar_width
            self.sidebar.style.margin_right = self.policy.gap
        else:
            del self.sidebar.style.width
            self.sidebar.style.margin_right = 0
        if list(self.view.children) != expected:
            self.view.clear()
            self.view.add(*expected)
        # Keep the toolbar stable on resize; a pinned tree needs no toggle.
        self.menu_button.enabled = not self.expanded
