"""Destination-local screens; native Back never closes an open document."""
import weakref
import toga
from toga.style import Pack
from toga.style.pack import COLUMN

_apple_delegate = None


def apple_delegate():
    global _apple_delegate
    if _apple_delegate is None:
        from rubicon.objc import ObjCClass, objc_method, objc_property

        class CommonUtilsRouteDelegate(ObjCClass('NSObject')):
            owner = objc_property(object, weak=True)

            @objc_method
            def navigationController_willShowViewController_animated_(self, navigation, controller, animated: bool) -> None:
                owner = self.owner
                if owner is not None and not owner.changing:
                    adapter = owner.host.adapter
                    if (navigation == adapter.controller.moreNavigationController
                            and adapter.is_destination_controller(controller)):
                        adapter.controller.navigationController_willShowViewController_animated_(navigation, controller, animated)

            @objc_method
            def navigationController_didShowViewController_animated_(self, navigation, controller, animated: bool) -> None:
                owner = self.owner
                if owner is not None:
                    owner.native_popped(navigation)

        _apple_delegate = CommonUtilsRouteDelegate
    return _apple_delegate


class Routes:
    def __init__(self, host, *, guard, changed, intent=None):
        self.host, self.guard, self.changed = host, guard, changed
        self.intent = intent
        self.roots = {key: toga.Box(style=Pack(direction=COLUMN, flex=1)) for key in host.destinations}
        self.screens = {key: [] for key in host.destinations}
        self.changing = False
        self.back_callback = None
        self.delegate = None
        self.on_render = None
        for key in host.destinations:
            host.bodies[key].add(self.roots[key])

    def body(self, destination=None):
        destination = destination or self.host.state.destination
        screens = self.screens[destination]
        return screens[-1][1] if screens else self.roots[destination]

    @property
    def apple(self):
        return self.host.adapter is not None and hasattr(self.host.adapter, 'navigation')

    def update_title(self, view, title):
        destination = self.host.state.destination
        screens = self.screens[destination]
        if self.apple and screens and view in self.body(destination).children:
            screens[-1][2].controller.title = title

    def install(self):
        if self.apple:
            self.delegate = apple_delegate().alloc().init()
            self.delegate.owner = self
            for navigation in self.host.adapter.navigation:
                navigation.delegate = self.delegate
            self.host.adapter.controller.moreNavigationController.delegate = self.delegate
        elif self.host.adapter is not None:
            from java import dynamic_proxy
            from io.github.ispaure.commonutils import NavigationBack

            class Listener(dynamic_proxy(NavigationBack.Listener)):
                def __init__(self, owner):
                    super().__init__()
                    self.owner = weakref.ref(owner)

                def onBackRequested(self):
                    owner = self.owner()
                    return owner.back() if owner is not None else False

            self.listener = Listener(self)
            self.back_callback = NavigationBack.install(self.host.adapter.impl._native_activity, self.listener)
        self.selection_changed()
        if self.on_render is not None:
            self.on_render()

    def uninstall(self):
        if self.delegate is not None and self.apple:
            for navigation in self.host.adapter.navigation:
                navigation.delegate = None
            self.host.adapter.controller.moreNavigationController.delegate = self.host.adapter.controller
            self.delegate = None
        if self.back_callback is not None:
            self.back_callback.remove()
            self.back_callback = None

    def selection_changed(self):
        if self.back_callback is not None:
            self.back_callback.setEnabled(bool(self.screens[self.host.state.destination]))
        self.changed(self.body())

    def show(self, view, *, destination=None, route=None, title='', root=False):
        destination = destination or self.host.state.destination
        self.host.activate(destination)
        screens = self.screens[destination]
        if root:
            self.trim(destination, 0)
        elif route is not None:
            existing = next((index for index, screen in enumerate(screens) if screen[0] == route), None)
            if existing is not None:
                self.trim(destination, existing + 1)
            else:
                panel = toga.Box(style=Pack(direction=COLUMN, flex=1))
                panel.add(view)
                pane = self.host.adapter.push(destination, panel, title) if self.apple else None
                screens.append((route, panel, pane))
                self.host.state.push(route)
        panel = self.body(destination)
        if list(panel.children) != [view]:
            old = list(panel.children)
            try:
                for child in old:
                    panel.remove(child)
                panel.add(view)
            except Exception:
                for child in list(panel.children):
                    panel.remove(child)
                for child in old:
                    panel.add(child)
                raise
        self.update_title(view, title)
        self.render(destination)

    def render(self, destination):
        if not self.apple:
            outer = self.host.bodies[destination]
            panel = self.body(destination)
            if list(outer.children) != [panel]:
                for child in list(outer.children):
                    outer.remove(child)
                outer.add(panel)
        self.selection_changed()
        if self.on_render is not None:
            self.on_render()

    def trim(self, destination, count, *, native=True):
        screens = self.screens[destination]
        self.changing = True
        try:
            if native and self.apple:
                navigation = self.host.adapter.navigation_for(destination)
                target = screens[count - 1][2].controller if count else self.host.adapter.containers[self.host.destinations.index(destination)][1]
                navigation.popToViewController(target, animated=False)
            for _, panel, pane in screens[count:]:
                if pane is not None:
                    self.host.adapter.release_pane(pane)
            del screens[count:]
            self.host.state.routes[destination] = [screen[0] for screen in screens]
        finally:
            self.changing = False

    def native_popped(self, navigation):
        if self.changing or self.host.changing:
            return
        destination = self.host.adapter.destination_for_navigation(navigation)
        if destination is None:
            return
        count = self.host.adapter.route_depth(navigation)
        if count < len(self.screens[destination]):
            if self.intent is not None:
                self.intent()
            self.trim(destination, count, native=False)
            self.selection_changed()

    def back(self):
        if not self.guard():
            return True
        destination = self.host.state.destination
        if not self.screens[destination]:
            return False
        if self.intent is not None:
            self.intent()
        self.trim(destination, len(self.screens[destination]) - 1)
        self.render(destination)
        return True
