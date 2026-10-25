"""Native bar visibility with restoration owned by the navigation host."""


class NavigationChrome:
    def __init__(self, host):
        self.host = host
        self.restore_callbacks = []
        self.context = None
        self.page_navigation = None
        self.page_gestures = []

    def restore_page_swipes(self):
        for gesture, enabled in self.page_gestures:
            gesture.setEnabled(enabled)
        self.page_gestures.clear()
        self.page_navigation = None

    def set_page_swipes(self, active, *, navigation=None):
        """Reserve horizontal gestures for reader paging, independently of bars."""
        adapter = self.host.adapter
        if adapter is None or not hasattr(adapter, 'navigation'):
            self.restore_page_swipes()
            return
        navigation = navigation or adapter.navigation_for(self.host.state.destination)
        if not active or navigation != self.page_navigation:
            self.restore_page_swipes()
        if not active:
            return
        from rubicon.objc import SEL
        self.page_navigation = navigation
        for name in ('interactivePopGestureRecognizer', 'interactiveContentPopGestureRecognizer'):
            if navigation.respondsToSelector(SEL(name)):
                gesture = getattr(navigation, name)
                if gesture is not None:
                    if not any(saved == gesture for saved, _ in self.page_gestures):
                        self.page_gestures.append((gesture, bool(gesture.isEnabled())))
                    gesture.setEnabled(False)

    def restore(self):
        self.restore_page_swipes()
        for callback in reversed(self.restore_callbacks):
            callback()
        self.restore_callbacks.clear()
        self.context = None
        adapter = self.host.adapter
        if adapter is not None and hasattr(adapter, 'refresh_keyboard_chrome'):
            adapter.refresh_keyboard_chrome()

    def set_hidden(self, hidden, *, navigation=None):
        adapter = self.host.adapter
        if adapter is None:
            return
        if hasattr(adapter, 'navigation'):
            navigation = navigation or adapter.navigation_for(self.host.state.destination)
        context = (self.host.state.destination, navigation)
        changed = self.context != context
        if not hidden or changed:
            self.restore()
        if not hidden:
            return
        if hasattr(adapter, 'restore_keyboard_chrome'):
            # Snapshot the application's bars, not temporary IME suppression.
            adapter.restore_keyboard_chrome()
        self.context = context
        capture = not self.restore_callbacks
        if hasattr(adapter, 'navigation'):
            from rubicon.objc import SEL
            controller = adapter.controller
            modern = bool(controller.respondsToSelector(SEL('setTabBarHidden:animated:')))
            previous = adapter.tabs_hidden()
            if capture:
                self.restore_callbacks.append(lambda: adapter.set_keyboard_tabs_hidden(modern, previous))
            adapter.set_keyboard_tabs_hidden(modern, True)
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

            # Hiding application bars alone leaves Android's status/navigation
            # insets consuming the reading viewport. Use immersive system bars
            # and restore each original visibility bit when leaving this route.
            from java import jclass
            WindowCompat = jclass('androidx.core.view.WindowCompat')
            ViewCompat = jclass('androidx.core.view.ViewCompat')
            Types = jclass('androidx.core.view.WindowInsetsCompat$Type')
            Controller = jclass('androidx.core.view.WindowInsetsControllerCompat')
            window = adapter.impl._native_activity.getWindow()
            decor = window.getDecorView()
            controller = WindowCompat.getInsetsController(window, decor)
            if capture:
                insets = ViewCompat.getRootWindowInsets(decor)
                states = [(kind, bool(insets.isVisible(kind)) if insets is not None else True)
                          for kind in (Types.statusBars(), Types.navigationBars())]
                behavior = controller.getSystemBarsBehavior()
                def restore_system_bars():
                    controller.setSystemBarsBehavior(behavior)
                    for kind, visible in states:
                        controller.show(kind) if visible else controller.hide(kind)
                    ViewCompat.requestApplyInsets(decor)
                self.restore_callbacks.append(restore_system_bars)
            controller.setSystemBarsBehavior(Controller.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE)
            controller.hide(Types.systemBars())
            ViewCompat.requestApplyInsets(decor)
