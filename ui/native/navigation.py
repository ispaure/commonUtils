"""Native navigation adapters for the pinned Toga 0.5.7 mobile hosts.

Backend access stays here. Neither feature controllers nor shared Python state
need to know about UIKit/Java containment, insets or navigation bar placement.
"""
from copy import copy

import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from .navigation_state import NavigationState
from .chrome import NavigationChrome


class NativeNavigationHost:
    def __init__(self, items, *, state=None, on_select=None, prefer_sidebar=True):
        items = tuple(items)
        if not 1 <= len(items) <= 7 or any(len(item) != 4 for item in items):
            raise ValueError('Supply one to seven (key, label, Apple symbol, Android icon) destinations.')
        self.destinations, self.labels, self.symbols, self.android_icons = map(tuple, zip(*items))
        self.state = state or NavigationState(self.destinations)
        if self.state.destinations != self.destinations:
            raise ValueError('Navigation state does not match destination items.')
        self.on_select = on_select
        self.prefer_sidebar = prefer_sidebar
        self.changing = False
        self._programmatic_overflow = None
        self.bodies = {key: toga.Box(style=Pack(direction=COLUMN, flex=1)) for key in self.destinations}
        self.root = toga.OptionContainer(style=Pack(flex=1))
        if len(items) > 5 and type(self.root._impl).__module__.startswith('toga_android.'):
            self._expand_android_bar()
        for key, label in zip(self.destinations, self.labels):
            self.root.content.append(label, self.bodies[key])
        self.root.on_select = self._selected
        self.adapter = None
        self.window = None
        self._installing_adapter = None
        self._install_call_active = False
        self.chrome = NavigationChrome(self)
        self.activate(self.state.destination)

    def _expand_android_bar(self):
        """Prepare the backend before it creates option references for item six."""
        from java import jclass
        from android.widget import LinearLayout
        impl = self.root._impl
        old = impl.native_navigationview
        old.setOnItemSelectedListener(None)
        old.removeOnLayoutChangeListener(impl.onLayoutChangeListener)
        impl.native.removeView(old)
        bar = jclass('io.github.ispaure.commonutils.ExpandedBottomNavigationView')(impl._native_activity)
        bar.setLabelVisibilityMode(2)
        bar.setOnItemSelectedListener(impl.onItemSelectedListener)
        bar.addOnLayoutChangeListener(impl.onLayoutChangeListener)
        impl.native.addView(bar, LinearLayout.LayoutParams(-1, -2))
        impl.native_navigationview = bar
        impl.max_items = bar.getMaxItemCount()

    def _selected(self, widget, **kwargs):
        if self.changing or widget.current_tab is None:
            return
        destination = self.destinations[widget.current_tab.index]
        if self._programmatic_overflow == destination:
            self._programmatic_overflow = None
            return
        self._programmatic_overflow = None
        if self.on_select is not None and self.on_select(destination) is False:
            self.activate(self.state.destination)
            return
        self.state.select(destination)

    def activate(self, destination):
        if destination not in self.destinations:
            raise ValueError('Unknown mobile destination.')
        index = self.destinations.index(destination)
        current = self.root.current_tab
        if current is not None and current.index == index:
            self.state.select(destination)
            return
        self._programmatic_overflow = None
        if (len(self.destinations) > 5 and index >= 4
                and type(self.root._impl).__module__.startswith('toga_iOS.')
                and getattr(self.root._impl, 'uses_more', False)
                and self.adapter is not None
                and len(list(self.adapter.controller.tabBar.items or ())) == 5):
            self._programmatic_overflow = destination
        self.changing = True
        try:
            self.root.current_tab = index
            self.state.select(destination)
        finally:
            self.changing = False

    def install(self, window):
        if getattr(self, '_install_call_active', False):
            raise RuntimeError('Navigation installation is in progress.')
        if getattr(self, '_installing_adapter', None) is not None:
            raise RuntimeError('Navigation cleanup is pending; uninstall before retrying.')
        if self.window is not None:
            raise RuntimeError('Navigation host is already installed.')
        self.window = window
        backend = type(self.root._impl).__module__
        apple = backend.startswith('toga_iOS.')
        changing = self.changing
        if apple:
            self.changing = True
            self._install_call_active = True
        try:
            if apple:
                adapter = AppleNavigation(self, window)
                if self.window is not window:
                    raise RuntimeError('Navigation was retired during installation.')
                self.adapter = adapter
            elif backend.startswith('toga_android.'):
                self.adapter = AndroidNavigation(self, window)
            self._installing_adapter = None
        except Exception as error:
            pending = getattr(self, '_installing_adapter', None)
            # A consumer may extend __init__ after Apple's base construction.
            # That completed adapter can use its normal (possibly extended)
            # disposer; the incomplete base already attempted staged rollback.
            if pending is not None and pending._construction_complete:
                try:
                    pending.dispose()
                    pending._construction_complete = False
                    pending._rollback_construction()
                except Exception:
                    try:
                        error.add_note('Apple navigation cleanup is pending; call host.uninstall() before retrying installation.')
                    except Exception:
                        pass
                else:
                    self._installing_adapter = None
            if getattr(self, '_installing_adapter', None) is None:
                self.window = None
            raise
        finally:
            if apple:
                self.changing = changing
                self._install_call_active = False

    def uninstall(self):
        pending = getattr(self, '_installing_adapter', None)
        if pending is not None:
            changing, self.changing = self.changing, True
            try:
                if pending._construction_complete:
                    pending.dispose()
                    pending._construction_complete = False
                pending._rollback_construction()
                self._installing_adapter = None
                self.window = None
            finally:
                self.changing = changing
            return
        self.chrome.restore()
        if self.adapter is not None:
            self.adapter.dispose()
            self.adapter = None
        self.window = None

    def dispose(self):
        self.uninstall()
        if type(self.root._impl).__module__.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            impl = self.root._impl
            ObjCClass('NSObject').cancelPreviousPerformRequestsWithTarget(impl.native_controller)
            impl.native_controller.delegate = None
            impl.native_controller.setViewControllers([], animated=False)
            for container in impl.sub_containers:
                container.controller.view = ObjCClass('UIView').alloc().init()
        self.on_select = None

    def diagnostics(self):
        return self.adapter.diagnostics() if self.adapter else {'platform': 'host'}


class AppleNavigation:
    def __init__(self, host, window):
        from rubicon.objc import ObjCClass, SEL
        self.host, self.window = host, window
        self.impl = host.root._impl
        self.controller = self.impl.native_controller
        self.parent = window._impl.container.content_controller
        self.old_layout = window._impl.container.on_native_layout
        self.old_get_size = window._impl.get_size
        self.old_additional_insets = copy(self.parent.additionalSafeAreaInsets)
        self.keyboard_live = False
        self.keyboard_visible = False
        self.keyboard_frame = None
        self.keyboard_tab_visibility = None
        self.keyboard_layout_pending = False
        self.keyboard_observer = None
        self.keyboard_focus_observers = []
        self._controllers_started = self._mode_started = self._window_hooks_started = False
        self._container_hooks_pending = False
        self._keyboard_restoration_pending = False
        self._construction_complete = False
        self.old_window_insets = tuple(getattr(window._impl.container, edge + '_inset')
                                       for edge in ('top', 'bottom', 'left', 'right'))
        # Retain the draft separately: consumer callbacks must not see it as an
        # installed adapter, but failed cleanup still needs an owner and a retry.
        host._installing_adapter = self
        try:
            self._install_keyboard_observer()
            self._window_hooks_started = True
            window._impl.container.on_native_layout = self._layout_window
            window._impl.get_size = self.get_size
            self._install_controllers()
            self.sidebar_available = bool(self.controller.respondsToSelector(SEL('setMode:')))
            self.sidebar_used = (self.sidebar_available and host.prefer_sidebar
                                 and ObjCClass('UIDevice').currentDevice.userInterfaceIdiom == 1)
            if self.sidebar_available:
                self.old_mode = int(self.controller.mode)
                self._mode_started = True
                self.controller.setMode(2 if self.sidebar_used else 1)
            self._keyboard_restoration_pending = True
            self.keyboard_live = True
            self._layout_window(window._impl.container)
            # Initial layout may synchronously retire this draft. Stop here,
            # before returning to a consumer constructor that acquires more UI.
            if host._installing_adapter is not self or not self.keyboard_live:
                raise RuntimeError('Navigation was retired during installation.')
        except Exception as error:
            try:
                self._rollback_construction()
            except Exception:
                # The host retains this inactive draft until uninstall succeeds.
                # Diagnostic formatting must never replace the original error.
                try:
                    error.add_note('Apple navigation cleanup is pending; call host.uninstall() before retrying installation.')
                except Exception:
                    pass
            else:
                host._installing_adapter = None
            raise
        self._construction_complete = True

    def _rollback_construction(self):
        # The draft has not reached the installed adapter slot. Full dispose requires
        # all stages to have completed, so retire only recorded acquisitions here.
        self.keyboard_live = False
        self.keyboard_visible = False
        self.keyboard_frame = None

        errors = []

        def restore(callback):
            # Native getters belong inside the guarded operation too.
            try:
                callback()
            except Exception as cleanup_error:
                errors.append(cleanup_error)

        restore(self._retire_keyboard_observers)
        if self._keyboard_restoration_pending:
            start = len(errors)
            restore(self.restore_keyboard_chrome)
            restore(lambda: setattr(self.parent, 'additionalSafeAreaInsets', self.old_additional_insets))
            if len(errors) == start:
                self._keyboard_restoration_pending = False
        if self._mode_started:
            start = len(errors)
            restore(lambda: self.controller.setMode(self.old_mode))
            if len(errors) == start:
                self._mode_started = False
        if self._controllers_started:
            start = len(errors)
            # Keep our inactive leaf callbacks installed while rebuilding native
            # containment; restore original callbacks only after geometry.
            for container, content, layout, title, image, frame, insets in self._old_containers:
                restore(lambda: setattr(container, 'controller', content))
                restore(lambda: setattr(content, 'title', title))
                restore(lambda: setattr(content.tabBarItem, 'image', image))
            restore(lambda: self.controller.setViewControllers(self._old_tabs, animated=False))
            restore(self._restore_more)
            restore(lambda: setattr(self.controller, 'selectedViewController', self._old_selection))
            restore(self._restore_parent)
            restore(lambda: self.outer_navigation.setNavigationBarHidden(self.old_bar_hidden, animated=False))
            for container, content, layout, title, image, frame, insets in self._old_containers:
                restore(lambda: setattr(container.native, 'frame', frame))
                for edge, inset in zip(('top', 'bottom', 'left', 'right'), insets):
                    restore(lambda: setattr(container, edge + '_inset', inset))
            if (len(errors) == start and not self._mode_started
                    and not self._keyboard_restoration_pending):
                self._controllers_started = False
                self.navigation.clear()
                self.containers.clear()
        if self._container_hooks_pending and not self._controllers_started:
            start = len(errors)
            for container, content, layout, title, image, frame, insets in self._old_containers:
                restore(lambda: setattr(container, 'on_native_layout', layout))
            if len(errors) == start:
                self._container_hooks_pending = False
        if (self._window_hooks_started and not self._controllers_started
                and not self._container_hooks_pending and not self._mode_started
                and not self._keyboard_restoration_pending):
            start = len(errors)
            container = self.window._impl.container
            for edge, inset in zip(('top', 'bottom', 'left', 'right'), self.old_window_insets):
                restore(lambda: setattr(container, edge + '_inset', inset))
            restore(lambda: setattr(container, 'on_native_layout', self.old_layout))
            restore(lambda: setattr(self.window._impl, 'get_size', self.old_get_size))
            if len(errors) == start:
                self._window_hooks_started = False
        if errors:
            raise ExceptionGroup('Apple navigation construction cleanup failed', errors)

    def _restore_more(self):
        more = self.controller.moreNavigationController
        if more != self._old_more:
            # Do not install UIKit's old private list controller in a new More
            # owner or silently claim that an unknown native tree was restored.
            raise RuntimeError('UIKit replaced the More controller during navigation construction.')
        if more is not None:
            more.setViewControllers(self._old_more_stack, animated=False)
            more.delegate = self._old_more_delegate

    def _restore_parent(self):
        parent = self.controller.parentViewController
        if parent == self._old_parent:
            return
        if self._old_parent is None and parent == self.parent:
            self.controller.willMoveToParentViewController(None)
            self.controller.removeFromParentViewController()
        else:
            raise RuntimeError('Navigation parent changed during construction cleanup.')

    def _retire_keyboard_observers(self):
        self.keyboard_live = False
        errors = []
        if self.keyboard_observer is not None:
            try:
                self.notification_center.removeObserver(self.keyboard_observer)
            except Exception as error:
                errors.append(error)
            else:
                self.keyboard_observer = None
        failed = []
        for observer in self.keyboard_focus_observers:
            try:
                self.notification_center.removeObserver(observer)
            except Exception as error:
                errors.append(error)
                failed.append(observer)
        # A native removal error must not erase the only handle for retry.
        self.keyboard_focus_observers = failed
        if errors:
            raise ExceptionGroup('Apple navigation observer retirement failed', errors)

    def _install_keyboard_observer(self):
        from rubicon.objc import ObjCClass, Block, objc_id
        self.keyboard_inset = 0
        self.keyboard_visible = False
        self.keyboard_tab_visibility = None
        self.keyboard_layout_pending = False
        self.keyboard_frame = None
        self.keyboard_block = Block(self.refresh_keyboard, None, objc_id)
        self.notification_center = ObjCClass('NSNotificationCenter').defaultCenter
        if callable(self.notification_center):
            self.notification_center = self.notification_center()
        self.keyboard_observer = self.notification_center.addObserverForName(
            'UIKeyboardDidChangeFrameNotification', object=None, queue=None, usingBlock=self.keyboard_block)
        self.keyboard_focus_block = Block(self.keyboard_focus_changed, None, objc_id)
        # Child windows acquire their UIWindowScene after adapter construction.
        # Filter scene notifications at delivery time rather than binding nil.
        for name, owner in (
                ('UIWindowDidBecomeKeyNotification', self.window._impl.native),
                ('UIWindowDidResignKeyNotification', self.window._impl.native),
                ('UISceneDidActivateNotification', None),
                ('UISceneWillDeactivateNotification', None)):
            observer = self.notification_center.addObserverForName(
                name, object=owner, queue=None, usingBlock=self.keyboard_focus_block)
            self.keyboard_focus_observers.append(observer)

    def _install_controllers(self):
        from rubicon.objc import ObjCClass
        self.outer_navigation = self.window._impl.native.rootViewController
        self.old_bar_hidden = bool(self.outer_navigation.isNavigationBarHidden())
        self._old_parent = self.controller.parentViewController
        if self._old_parent is not None and self._old_parent != self.parent:
            raise ValueError('Navigation controller already belongs to another parent.')
        self._old_tabs = list(self.controller.viewControllers or ())
        self._old_selection = self.controller.selectedViewController
        self._old_more = self.controller.moreNavigationController
        self._old_more_delegate = self._old_more.delegate if self._old_more is not None else None
        self._old_more_stack = list(self._old_more.viewControllers or ()) if self._old_more is not None else []
        self._old_containers = [(container, container.controller, container.on_native_layout,
                                 container.controller.title, container.controller.tabBarItem.image,
                                 copy(container.native.frame),
                                 tuple(getattr(container, edge + '_inset') for edge in ('top', 'bottom', 'left', 'right')))
                                for container in self.impl.sub_containers]
        self.containers = []
        self.panes = []
        self.navigation = []
        self._controllers_started = True
        self._container_hooks_pending = True
        for container in self.impl.sub_containers:
            container.on_native_layout = self._layout_content
        self.outer_navigation.setNavigationBarHidden(True, animated=False)
        # Toga normally attaches only the controller's view. Managed containment
        # is required for native safe areas, bars and appearance callbacks.
        if self.controller.parentViewController != self.parent:
            self.parent.addChildViewController(self.controller)
            self.controller.didMoveToParentViewController(self.parent)
        self.controller.setViewControllers([], animated=False)
        symbols = self.host.symbols
        for label, symbol, container in zip(self.host.labels, symbols, self.impl.sub_containers):
            content = container.controller
            content.title = label
            navigation = ObjCClass('UINavigationController').alloc().initWithRootViewController(content)
            self.navigation.append(navigation)
            navigation.tabBarItem = content.tabBarItem
            navigation.tabBarItem.image = ObjCClass('UIImage').systemImageNamed(symbol)
            container.controller = navigation
            self.containers.append((container, content))
        self.impl.refresh_tabs()

    def get_size(self):
        if not self.keyboard_live:
            return self.old_get_size()
        from toga.types import Size
        bounds = self.window._impl.native.bounds.size
        return Size(int(bounds.width), int(bounds.height))

    def _layout_content(self, container):
        # Keep the static content hook compatible with consumer extensions, but
        # gate native dispatch before invoking any extension's additional work.
        if self.keyboard_live:
            self.layout_content(container)

    def _layout_window(self, container):
        if self.keyboard_live:
            self.layout_window(container)

    @staticmethod
    def layout_content(container):
        # A controller root must fill its UIKit host. Bar/split transitions can
        # leave a nonzero but stale frame (and even a width from an old Pack
        # minimum). Repair it on every layout, not only the initial zero frame.
        # Safe-area insets below reserve the visible bars exactly once.
        controller = container.controller
        navigation = controller.navigationController
        if callable(navigation):
            navigation = navigation()
        parent = navigation.view if navigation is not None else controller.view
        if parent is not None:
            bounds = parent.bounds
            frame = container.native.frame
            if (bounds.size.width > 0 and bounds.size.height > 0
                    and (abs(frame.origin.x - bounds.origin.x) > .01
                         or abs(frame.origin.y - bounds.origin.y) > .01
                         or abs(frame.size.width - bounds.size.width) > .01
                         or abs(frame.size.height - bounds.size.height) > .01)):
                container.native.frame = bounds
        size = container.native.bounds.size
        if size.width <= 0 or size.height <= 0:
            controller = container.controller
            navigation = controller.navigationController
            bounds = (navigation.view.bounds if navigation is not None else controller.view.bounds)
            if bounds.size.width > 0 and bounds.size.height > 0:
                container.native.frame = bounds
        insets = container.native.safeAreaInsets
        container.top_inset, container.bottom_inset = insets.top, insets.bottom
        container.left_inset, container.right_inset = insets.left, insets.right
        if container.content is not None:
            container.content.interface.refresh()

    def layout_window(self, container):
        if not self.keyboard_live:
            return
        # This root hosts native navigation controllers, which own safe areas.
        # Subtracting their bar insets here too repeatedly shrinks the tab/split
        # controller during show/hide transitions. Leaf containers apply them.
        container.top_inset = container.bottom_inset = 0
        container.left_inset = container.right_inset = 0
        self.window._impl.notify_resize(container)

    def refresh_keyboard(self, notification):
        if not self.keyboard_live:
            return
        from rubicon.objc import ObjCInstance
        value = ObjCInstance(notification).userInfo.objectForKey('UIKeyboardFrameEndUserInfoKey')
        if not value:
            return
        frame = value.CGRectValue
        if callable(frame):
            frame = frame()
        self.keyboard_frame = frame
        self.apply_keyboard_frame(frame)

    def keyboard_focus_changed(self, notification):
        if not self.keyboard_live:
            return
        from rubicon.objc import ObjCInstance
        owner = ObjCInstance(notification).object
        native = self.window._impl.native
        if owner is not None and (owner == native or owner == native.windowScene):
            # WillDeactivate can arrive before activationState changes.
            self.window.app.loop.call_soon(self.refresh_keyboard_focus)

    def refresh_keyboard_focus(self):
        if self.keyboard_live and self.keyboard_frame is not None:
            self.apply_keyboard_frame(self.keyboard_frame)

    def apply_keyboard_frame(self, frame):
        # Convert from the owning window's screen, never UIScreen.main. Floating
        # iPad keyboards do not consume a full-width bottom inset.
        native = self.window._impl.native
        scene = native.windowScene
        frame = native.convertRect(frame, fromCoordinateSpace=native.screen.coordinateSpace)
        frame = self.parent.view.convertRect(frame, fromView=native)
        bounds = self.parent.view.bounds.size
        intersects = (bool(native.isKeyWindow()) and scene is not None and int(scene.activationState) == 0
                      and frame.size.height > 0
                      and frame.origin.y < bounds.height and frame.origin.y + frame.size.height > 0
                      and frame.origin.x < bounds.width and frame.origin.x + frame.size.width > 0)
        self.keyboard_visible = intersects
        self.refresh_keyboard_chrome()
        docked = intersects and frame.origin.y + frame.size.height >= bounds.height - 1
        cover = max(0, bounds.height - max(0, frame.origin.y)) if docked else 0
        baseline = max(0, self.parent.view.safeAreaInsets.bottom - self.keyboard_inset)
        overlap = max(0, float(cover) - float(baseline))
        if abs(overlap - self.keyboard_inset) > .5:
            insets = self.parent.additionalSafeAreaInsets
            insets.bottom = self.old_additional_insets.bottom + overlap
            self.keyboard_inset = overlap
            self.parent.additionalSafeAreaInsets = insets
            self.parent.view.setNeedsLayout()
            self.queue_keyboard_layout()

    def queue_keyboard_layout(self):
        if self.keyboard_live and not self.keyboard_layout_pending:
            self.keyboard_layout_pending = True
            self.window.app.loop.call_soon(self.layout_keyboard)

    def layout_keyboard(self):
        self.keyboard_layout_pending = False
        if self.keyboard_live:
            self.parent.view.layoutIfNeeded()
            # Keyboard/bar geometry changes without changing the window size,
            # so Toga would otherwise suppress the consumer resize callback.
            self.window.on_resize()

    def tabs_hidden(self):
        from rubicon.objc import SEL
        if self.controller.respondsToSelector(SEL('setTabBarHidden:animated:')):
            return bool(self.controller.isTabBarHidden())
        return bool(self.controller.tabBar.isHidden())

    def refresh_keyboard_chrome(self):
        if not self.keyboard_live or not self.keyboard_visible or self.host.chrome.context is not None:
            self.restore_keyboard_chrome()
            return
        if self.keyboard_tab_visibility is None:
            from rubicon.objc import SEL
            modern = bool(self.controller.respondsToSelector(SEL('setTabBarHidden:animated:')))
            hidden = bool(self.controller.isTabBarHidden() if modern else self.controller.tabBar.isHidden())
            self.keyboard_tab_visibility = (modern, hidden)
            self.set_keyboard_tabs_hidden(modern, True)

    def set_keyboard_tabs_hidden(self, modern, hidden):
        # A hidden tab bar alone leaves iPad's sidebar and its toggle available.
        # Temporarily use tab-only mode, retaining the user's sidebar state for
        # route/keyboard/fullscreen restoration through this same entry point.
        changed = False
        if getattr(self, 'sidebar_used', False):
            saved = getattr(self, '_sidebar_visibility', None)
            if hidden:
                if saved is None:
                    self._sidebar_visibility = (int(self.controller.mode),
                                                bool(self.controller.sidebar.isHidden()))
                if not self.controller.sidebar.isHidden():
                    self.controller.sidebar.setHidden(True)
                    changed = True
                if int(self.controller.mode) != 1:
                    self.controller.setMode(1)
                    changed = True
            elif saved is not None:
                mode, sidebar_hidden = saved
                if int(self.controller.mode) != mode:
                    self.controller.setMode(mode)
                    changed = True
                if bool(self.controller.sidebar.isHidden()) != sidebar_hidden:
                    self.controller.sidebar.setHidden(sidebar_hidden)
                    changed = True
                self._sidebar_visibility = None
        current = self.controller.isTabBarHidden() if modern else self.controller.tabBar.isHidden()
        if bool(current) != hidden:
            if modern:
                # UIKit also releases the tab bar's safe-area reservation.
                self.controller.setTabBarHidden(hidden, animated=False)
            else:
                self.controller.tabBar.setHidden(hidden)
            changed = True
        # Fullscreen readers reassert their bar policy during every resize.
        # An unchanged policy must not schedule another resize of its own.
        if changed:
            self.controller.view.setNeedsLayout()
            self.parent.view.setNeedsLayout()
            self.queue_keyboard_layout()

    def restore_keyboard_chrome(self):
        if self.keyboard_tab_visibility is not None:
            modern, hidden = self.keyboard_tab_visibility
            self.set_keyboard_tabs_hidden(modern, hidden)
            self.keyboard_tab_visibility = None

    def navigation_for(self, destination):
        """UIKit More can move a tab's root into its own navigation stack."""
        index = self.host.destinations.index(destination)
        root = self.containers[index][1]
        return root.navigationController or self.navigation[index]

    def content_controller(self, destination):
        index = self.host.destinations.index(destination)
        navigation = self.navigation_for(destination)
        return navigation.topViewController or self.containers[index][1]

    def is_destination_controller(self, controller):
        return any(controller == root or controller == navigation
                   for (_, root), navigation in zip(self.containers, self.navigation))

    def is_more_navigation(self, navigation):
        # Accessing UIKit's overflow controller can lazily create and lay out
        # its list. Normal tab transitions already identify their own stack.
        return navigation not in self.navigation and navigation == self.controller.moreNavigationController

    def destination_for_navigation(self, navigation):
        if navigation in self.navigation:
            return self.host.destinations[self.navigation.index(navigation)]
        if self.is_more_navigation(navigation):
            stack = list(navigation.viewControllers)
            for index, (_, root) in enumerate(self.containers):
                if root in stack:
                    return self.host.destinations[index]
            return None  # The overflow list itself has no document route.
        raise ValueError('Unknown Apple navigation controller.')

    def route_depth(self, navigation):
        # More's own list precedes the selected tab's root.
        root_count = 2 if self.is_more_navigation(navigation) else 1
        return max(0, len(navigation.viewControllers) - root_count)

    def push(self, destination, widget, title):
        from toga_iOS.container import ControlledContainer
        container = ControlledContainer(on_refresh=lambda value: None,
                                        on_native_layout=self._layout_content)
        widget.app = self.window.app
        widget.window = self.window
        container.content = widget._impl
        container.controller.title = title
        self.panes.append(container)
        self.navigation_for(destination).pushViewController(container.controller, animated=False)
        return container

    def pop(self, destination):
        return self.navigation_for(destination).popViewControllerAnimated(False)

    def release_pane(self, container):
        from rubicon.objc import ObjCClass
        container.controller.view = ObjCClass('UIView').alloc().init()
        if container.content is not None:
            container.content.interface.window = None
            container.content.interface.app = None
        container.content = None
        if container in self.panes:
            self.panes.remove(container)

    def prove_split(self, leading, detail):
        from rubicon.objc import ObjCClass
        from toga_iOS.container import ControlledContainer
        split = ObjCClass('UISplitViewController').alloc().initWithStyle(1)  # doubleColumn
        containers = []
        for column, widget in zip((0, 2), (leading, detail)):
            container = ControlledContainer(on_refresh=lambda value: None,
                                            on_native_layout=self._layout_content)
            widget.app = self.window.app
            widget.window = self.window
            container.content = widget._impl
            containers.append(container)
            split.setViewController(container.controller, forColumn=column)
        split.preferredDisplayMode = 2  # oneBesideSecondary
        self.panes.extend(containers)
        self.split = split
        # Exercise as a full-screen native presentation, avoiding unsupported
        # split-controller nesting inside an OptionContainer tab.
        split.modalPresentationStyle = 0  # fullScreen
        self.controller.presentViewController(split, animated=False, completion=None)
        return containers

    def diagnostics(self):
        from rubicon.objc import ObjCClass
        bounds = self.window._impl.native.bounds.size
        bar = self.controller.tabBar.frame.size
        application = ObjCClass('UIApplication').sharedApplication
        if callable(application):
            application = application()
        return dict(platform='ios', native_tabs=str(self.controller.objc_class.name),
                    contained=self.controller.parentViewController == self.parent,
                    sidebar_available=self.sidebar_available,
                    sidebar_used=self.sidebar_used,
                    width=float(bounds.width), height=float(bounds.height),
                    bar_axis='vertical' if bar.height > bar.width else 'horizontal',
                    application_active=int(application.applicationState) == 0,
                    keyboard_inset=self.keyboard_inset,
                    main_thread=bool(ObjCClass('NSThread').isMainThread))

    def dispose(self):
        self.keyboard_live = False
        self.keyboard_visible = False
        self._retire_keyboard_observers()
        self.keyboard_frame = None
        self.restore_keyboard_chrome()
        self.parent.additionalSafeAreaInsets = self.old_additional_insets
        if getattr(self, 'split', None):
            self.split.dismissViewControllerAnimated(False, completion=None)
        for container in self.panes:
            from rubicon.objc import ObjCClass
            container.controller.view = ObjCClass('UIView').alloc().init()
            container.on_native_layout = None
            if container.content is not None:
                container.content.interface.window = None
                container.content.interface.app = None
            container.content = None
        self.panes.clear()
        self.window._impl.container.on_native_layout = self.old_layout
        self.window._impl.get_size = self.old_get_size
        self.outer_navigation.setNavigationBarHidden(self.old_bar_hidden, animated=False)
        for container, content in self.containers:
            container.controller = content
            container.on_native_layout = None
        self.impl.refresh_tabs()
        self._restore_parent()


class AndroidNavigation:
    def __init__(self, host, window):
        self.host, self.window = host, window
        self.active = True
        # Admit the window before replacing any of Toga's native controls.
        self.old_window_resize = window.on_resize
        self.impl = host.root._impl
        self.old_min_height = host.root._MIN_HEIGHT
        # OptionContainer's default 100-point floor can exceed the entire
        # keyboard-sized window and push its children behind the IME.
        host.root._MIN_HEIGHT = 0
        self.impl.rehint()
        self._replace_bottom_bar()
        self.rail = None
        self.old_resize = self.impl.resize_tab_content
        self.old_refreshed = self.impl.refreshed
        self.native_window = self.impl._native_activity.getWindow()
        self.old_soft_input = self.native_window.getAttributes().softInputMode
        from android.view import WindowManager
        self.native_window.setSoftInputMode((self.old_soft_input & ~WindowManager.LayoutParams.SOFT_INPUT_MASK_ADJUST)
                                           | WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        self.layout_events = 0
        self.keyboard_chrome = None
        self.mode = 'bottom'
        self.old_listener = self.impl.onItemSelectedListener
        self._install_selection_listener()
        self.bottom.setOnItemSelectedListener(self.impl.onItemSelectedListener)
        self.impl.resize_tab_content = self.resize_content
        self.impl.refreshed = self.content_refreshed
        # GONE navigation bars do not receive a layout event themselves.
        # Watch the content viewport so hiding/restoring chrome still relayouts
        # the Python widgets after Android has reclaimed the actual space.
        self.impl.native_content.addOnLayoutChangeListener(self.impl.onLayoutChangeListener)
        window.on_resize = self.window_resized
        self._populate_bottom_menu()
        self.select_current_tab()
        self.window_resized(window)

    def _replace_bottom_bar(self):
        # The pinned backend constructs Material navigation with an AppCompat
        # context. Its fallback surface can be black while inactive items are
        # also black. Give both native presentations the same Material theme.
        from android.view import ContextThemeWrapper
        from android.widget import LinearLayout
        from com.google.android.material import R as MaterialR
        from com.google.android.material.bottomnavigation import BottomNavigationView
        self.original_bottom = self.impl.native_navigationview
        self.original_bottom.setOnItemSelectedListener(None)
        self.original_bottom.removeOnLayoutChangeListener(self.impl.onLayoutChangeListener)
        self.impl.native.removeView(self.original_bottom)
        context = ContextThemeWrapper(self.impl._native_activity,
            MaterialR.style.Theme_MaterialComponents_DayNight)
        if len(self.host.destinations) > 5:
            from java import jclass
            self.bottom = jclass('io.github.ispaure.commonutils.ExpandedBottomNavigationView')(context)
        else:
            self.bottom = BottomNavigationView(context)
        # Material 1.12's default inset listener treats the IME bottom inset as
        # navigation padding. Under adjustResize that grows this WRAP_CONTENT
        # bar to the whole remaining viewport and gives the content zero height.
        # The window/navigation host already reserves system and keyboard space.
        from java import jclass
        jclass('androidx.core.view.ViewCompat').setOnApplyWindowInsetsListener(self.bottom, None)
        self.bottom.setLabelVisibilityMode(2 if len(self.host.destinations) > 5 else 1)
        self.bottom.addOnLayoutChangeListener(self.impl.onLayoutChangeListener)
        self.impl.native.addView(self.bottom, LinearLayout.LayoutParams(-1, -2))
        self.impl.native_navigationview = self.bottom

    def _install_selection_listener(self):
        from com.google.android.material.navigation import NavigationBarView
        from java import dynamic_proxy
        import weakref
        class SelectionListener(dynamic_proxy(NavigationBarView.OnItemSelectedListener)):
            def __init__(self, adapter):
                super().__init__()
                self.adapter = weakref.ref(adapter)

            def onNavigationItemSelected(self, item):
                owner = self.adapter()
                if owner is None or not owner.active:
                    return False
                index = next((index for index, option in enumerate(owner.impl.options)
                              if option.menu_item == item), None)
                if index is None:
                    return False
                destination = owner.host.destinations[index]
                if owner.host.on_select and owner.host.on_select(destination) is False:
                    return False
                # Material calls its listener before checking the new item.
                # Reading Toga.current_tab inside that callback sees the old tab.
                owner.host.changing = True
                try:
                    owner.host.state.select(destination)
                    owner.impl.set_current_tab_index(index, programmatic=False)
                finally:
                    owner.host.changing = False
                return True

        self.impl.onItemSelectedListener = SelectionListener(self)

    def _populate_bottom_menu(self):
        from android import R
        resources = [None if name == 'home' else getattr(R.drawable, name) for name in self.host.android_icons]
        self.bottom.getMenu().clear()
        for index, (option, resource) in enumerate(zip(self.impl.options, resources)):
            option.menu_item = self.bottom.getMenu().add(0, index + 1, index, option.text)
            option.menu_item.setIcon(resource if resource is not None else self.home_icon())

    def select_current_tab(self):
        # Toga publishes on_select even for programmatic native selection.
        changing, self.host.changing = self.host.changing, True
        try:
            self.impl.set_current_tab_index(self.host.destinations.index(self.host.state.destination))
        finally:
            self.host.changing = changing

    @staticmethod
    def home_icon():
        from .icons import IconSpec, android_drawable
        spec = IconSpec('', '', (((2, 11), (12, 3), (22, 11)),
            ((5, 9), (5, 21), (9, 21), (9, 14), (15, 14), (15, 21), (19, 21), (19, 9))), stroke_width=1.6)
        drawable = android_drawable(spec)
        drawable.setIntrinsicWidth(24)
        drawable.setIntrinsicHeight(24)
        return drawable

    def window_resized(self, window, **kwargs):
        if not self.active:
            return
        self.layout_events += 1
        # Consumers must see the current IME state before laying out editors;
        # otherwise one frame still uses full-height controls in a short pane.
        self.update_keyboard_inset()
        if self.old_window_resize:
            # Toga's getter returns a wrapper already bound to this window.
            self.old_window_resize(**kwargs)
        width = self.impl.scale_out(self.impl.native.getWidth())
        if width > 0:
            self.set_mode('rail' if width >= 600 else 'bottom')

    def update_keyboard_inset(self):
        from android.graphics import Rect
        from java import jclass
        visible, own = Rect(), Rect()
        self.impl.native.getWindowVisibleDisplayFrame(visible)
        self.impl.native.getGlobalVisibleRect(own)
        overlap = max(0, own.bottom - visible.bottom)
        if self.impl.native.getPaddingBottom() != overlap:
            self.impl.native.setPadding(0, 0, 0, overlap)
        insets = jclass('androidx.core.view.ViewCompat').getRootWindowInsets(self.impl.native)
        keyboard = bool(insets and insets.isVisible(jclass('androidx.core.view.WindowInsetsCompat$Type').ime()))
        if self.host.chrome.context is not None:
            # Immersive readers own their restoration snapshot independently.
            self.restore_keyboard_chrome()
            return
        # On short phones/landscape, application bars can consume almost all
        # of the resized viewport. Give that space to the focused control.
        # Latch until dismissal: hiding bars itself changes the measured height.
        if keyboard and self.keyboard_chrome is None and visible.height() < self.impl.scale_in(400):
            bar = self.impl.native_navigationview
            title = self.impl._native_activity.getSupportActionBar()
            self.keyboard_chrome = (bar, bar.getVisibility(), title, bool(title and title.isShowing()))
            bar.setVisibility(8)
            if title is not None:
                title.hide()
        elif not keyboard:
            self.restore_keyboard_chrome()

    def restore_keyboard_chrome(self):
        if self.keyboard_chrome is not None:
            bar, visibility, title, showing = self.keyboard_chrome
            self.keyboard_chrome = None
            bar.setVisibility(visibility)
            if title is not None and showing:
                title.show()

    def transfer_keyboard_chrome(self, view):
        if self.keyboard_chrome is not None:
            previous, visibility, title, showing = self.keyboard_chrome
            # A cached inactive bar must not retain temporary GONE visibility
            # when rotation later mounts it again after keyboard dismissal.
            previous.setVisibility(visibility)
            self.keyboard_chrome = (view, visibility, title, showing)
            view.setVisibility(8)

    def set_mode(self, mode):
        from android.widget import LinearLayout
        from com.google.android.material.navigationrail import NavigationRailView
        from android.view import ContextThemeWrapper
        from com.google.android.material import R as MaterialR
        if mode == self.mode:
            return
        if mode not in {'rail', 'bottom'}:
            raise ValueError('Invalid Android navigation presentation.')
        old = self.impl.native_navigationview
        old.setOnItemSelectedListener(None)
        self.impl.native.removeView(old)
        if mode == 'rail':
            if self.rail is None:
                context = ContextThemeWrapper(self.impl._native_activity,
                    MaterialR.style.Theme_MaterialComponents_DayNight)
                self.rail = NavigationRailView(context)
                self.rail.setLabelVisibilityMode(1)  # LABEL_VISIBILITY_LABELED
                for index, label in enumerate(self.host.labels):
                    self.rail.getMenu().add(0, index + 1, index, label).setIcon(
                        self.bottom.getMenu().getItem(index).getIcon())
            view = self.rail
            self.impl.native.setOrientation(LinearLayout.HORIZONTAL)
            self.impl.native_content.setLayoutParams(LinearLayout.LayoutParams(0, -1, 1))
            self.impl.native.addView(view, 0, LinearLayout.LayoutParams(-2, -1))
        else:
            view = self.bottom
            self.impl.native.setOrientation(LinearLayout.VERTICAL)
            self.impl.native_content.setLayoutParams(LinearLayout.LayoutParams(-1, 0, 1))
            self.impl.native.addView(view, LinearLayout.LayoutParams(-1, -2))
        self.mode = mode
        self.impl.native_navigationview = view
        self.transfer_keyboard_chrome(view)
        for index, option in enumerate(self.impl.options):
            option.menu_item = view.getMenu().getItem(index)
        self.select_current_tab()
        view.setOnItemSelectedListener(self.impl.onItemSelectedListener)
        self.impl.native.requestLayout()

    def resize_content(self):
        if not self.active:
            return
        native = self.impl.native_content
        width, height = native.getWidth(), native.getHeight()
        if width and height:
            self.impl.resize_content(width, height)

    def content_refreshed(self):
        if not self.active:
            return
        # Container.refreshed replaces MATCH_PARENT/weight dimensions with the
        # previous measured content size. In rail mode this freezes the height
        # before system bars disappear; its weighted width also keeps the old
        # rail allocation. Let LinearLayout own both dimensions after Pack has
        # updated the children, so native resize events reach the whole reader.
        from android.widget import LinearLayout
        self.old_refreshed()
        native = self.impl.native_content
        params = native.getLayoutParams()
        width, height = (0, -1) if self.mode == 'rail' else (-1, 0)
        if params.width != width or params.height != height or params.weight != 1:
            native.setLayoutParams(LinearLayout.LayoutParams(width, height, 1))

    def diagnostics(self):
        from android.os import Looper
        view = self.impl.native_navigationview
        return dict(platform='android', native_tabs=str(view.getClass().getName()),
                    mode=self.mode, width=self.impl.scale_out(self.impl.native.getWidth()),
                    height=self.impl.scale_out(self.impl.native.getHeight()),
                    content_height=self.impl.scale_out(self.impl.native_content.getHeight()),
                    keyboard_inset=self.impl.scale_out(self.impl.native.getPaddingBottom()),
                    layout_events=self.layout_events,
                    main_thread=Looper.myLooper() == Looper.getMainLooper())

    def dispose(self):
        self.active = False
        self.restore_keyboard_chrome()
        self.set_mode('bottom')
        from android.widget import LinearLayout
        self.bottom.setOnItemSelectedListener(None)
        self.bottom.removeOnLayoutChangeListener(self.impl.onLayoutChangeListener)
        self.impl.native_content.removeOnLayoutChangeListener(self.impl.onLayoutChangeListener)
        self.impl.native.removeView(self.bottom)
        self.impl.native.addView(self.original_bottom, LinearLayout.LayoutParams(-1, -2))
        self.impl.native_navigationview = self.original_bottom
        for index, option in enumerate(self.impl.options):
            option.menu_item = self.original_bottom.getMenu().getItem(index)
        self.original_bottom.addOnLayoutChangeListener(self.impl.onLayoutChangeListener)
        self.impl.onItemSelectedListener = self.old_listener
        self.original_bottom.setOnItemSelectedListener(self.old_listener)
        self.select_current_tab()
        self.impl.resize_tab_content = self.old_resize
        self.impl.refreshed = self.old_refreshed
        from toga.handlers import NativeHandler
        self.window.on_resize = NativeHandler(self.old_window_resize)
        self.native_window.setSoftInputMode(self.old_soft_input)
        self.host.root._MIN_HEIGHT = self.old_min_height
        self.impl.rehint()
        self.impl.native.setPadding(0, 0, 0, 0)
        if self.rail is not None:
            self.rail.setOnItemSelectedListener(None)
