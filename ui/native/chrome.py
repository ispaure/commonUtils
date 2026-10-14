"""Native bar visibility with restoration owned by the navigation host."""


class NavigationChrome:
    def __init__(self, host):
        self.host = host
        self.restore_callbacks = []
        self.context = None

    def restore(self):
        for callback in reversed(self.restore_callbacks):
            callback()
        self.restore_callbacks.clear()
        self.context = None

    def set_hidden(self, hidden, *, navigation=None):
        adapter = self.host.adapter
        if adapter is None:
            return
        if hasattr(adapter, 'navigation'):
            navigation = navigation or adapter.navigation[self.host.destinations.index(self.host.state.destination)]
        context = (self.host.state.destination, navigation)
        changed = self.context != context
        if not hidden or changed:
            self.restore()
        if not hidden:
            return
        self.context = context
        capture = not self.restore_callbacks
        if hasattr(adapter, 'navigation'):
            from rubicon.objc import SEL
            controller, tab = adapter.controller, adapter.controller.tabBar
            if controller.respondsToSelector(SEL('setTabBarHidden:animated:')):
                previous = bool(controller.isTabBarHidden())
                if capture:
                    self.restore_callbacks.append(lambda: controller.setTabBarHidden(previous, animated=False))
                controller.setTabBarHidden(True, animated=False)
            else:
                previous = bool(tab.isHidden())
                if capture:
                    self.restore_callbacks.append(lambda: tab.setHidden(previous))
                tab.setHidden(True)
            previous_nav = bool(navigation.isNavigationBarHidden())
            if capture:
                self.restore_callbacks.append(lambda: navigation.setNavigationBarHidden(previous_nav, animated=False))
            navigation.setNavigationBarHidden(True, animated=False)
            controller.view.setNeedsLayout()
        elif hasattr(adapter.impl, 'native_navigationview'):
            bar = adapter.impl.native_navigationview
            previous = bar.getVisibility()
            if capture:
                self.restore_callbacks.append(lambda: bar.setVisibility(previous))
            bar.setVisibility(8)
            title = adapter.impl._native_activity.getSupportActionBar()
            if title is not None:
                visible = title.isShowing()
                if capture:
                    self.restore_callbacks.append(lambda: title.show() if visible else title.hide())
                title.hide()
