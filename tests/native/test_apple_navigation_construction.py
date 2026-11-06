"""Apple constructor failure prefixes using a fake bridge, never UIKit evidence."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import sys
import unittest
from contextlib import contextmanager, nullcontext
from importlib.util import find_spec
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

HAS_TOGA = find_spec('toga') is not None
if HAS_TOGA:
    from commonUtils.ui.native import navigation


class Bridge:
    """Records explicit native mutations; does not model UIKit's implicit More tree."""
    def __init__(self, failure=None):
        self.failure = failure
        self.error = RuntimeError(failure or 'failure')
        self.events, self.observers, self.removed, self.blocks = [], [], [], []
        self.active = set()
        self.fail_remove = False
        self.remove_failures = {}
        self.block_count = 0
        self.contents = [NS(title='Original ' + str(i), tabBarItem=NS(image=object())) for i in range(2)]
        self.containers = [NS(controller=content, on_native_layout=object(),
                              native=NS(frame=NS(origin=NS(x=0, y=0), size=NS(width=100, height=100))),
                              top_inset=1, bottom_inset=2, left_inset=3, right_inset=4)
                           for content in self.contents]
        self.parent = NS(additionalSafeAreaInsets=NS(bottom=7))
        self.controller = NS(parentViewController=None, viewControllers=list(self.contents), mode=0)
        self.controller.respondsToSelector = lambda sel: True
        self.controller.setMode = lambda mode: self.mutate('mode', self.controller, 'mode', mode)
        self.controller.didMoveToParentViewController = lambda parent: self.point('did_move')
        self.controller.willMoveToParentViewController = lambda parent: self.point('will_move')
        self.controller.removeFromParentViewController = lambda: self.mutate('detach', self.controller, 'parentViewController', None)
        self.controller.setViewControllers = lambda values, **kwargs: self.mutate('tabs', self.controller, 'viewControllers', list(values))
        self.controller.selectedViewController = self.contents[1]
        self.controller.moreNavigationController = NS(viewControllers=[object()], delegate=object())
        more = self.controller.moreNavigationController
        more.setViewControllers = lambda values, **kwargs: self.mutate('more', more, 'viewControllers', list(values))
        self.parent.addChildViewController = lambda controller: self.mutate('containment', controller, 'parentViewController', self.parent)
        self.outer = NS(hidden=False)
        self.outer.isNavigationBarHidden = lambda: self.outer.hidden
        self.outer.setNavigationBarHidden = lambda hidden, **kwargs: self.mutate('outer_bar', self.outer, 'hidden', hidden)
        self.root_container = NS(content_controller=self.parent, on_native_layout=object(),
                                 top_inset=1, bottom_inset=2, left_inset=3, right_inset=4)
        self.window = NS(_impl=NS(container=self.root_container, get_size=Mock(return_value=(400, 800)),
                                 native=NS(rootViewController=self.outer, bounds=NS(size=NS(width=400, height=800)))),
                         app=NS(loop=NS(call_soon=lambda f: self.events.append(('queued', f)))))
        self.window._impl.notify_resize = lambda container: self.point('resize')
        self.impl = NS(native_controller=self.controller, sub_containers=self.containers)
        self.impl.refresh_tabs = self.refresh_tabs
        self.host = NS(root=NS(_impl=self.impl), labels=('First', 'Second'), symbols=('house', 'doc'),
                       prefer_sidebar=True, changing=False, chrome=NS(context=None))
        self.original_layout = self.root_container.on_native_layout
        self.original_get_size = self.window._impl.get_size
        self.original_callbacks = [c.on_native_layout for c in self.containers]
        self.original_images = [c.tabBarItem.image for c in self.contents]
        self.created = []

    def point(self, name):
        self.events.append(name)
        if self.failure == name:
            self.failure = None  # One failure; recovery calls can run.
            raise self.error

    def mutate(self, name, obj, attr, value):
        setattr(obj, attr, value)
        self.point(name)  # Native side effect may precede the bridge error.

    def refresh_tabs(self):
        self.controller.viewControllers = [c.controller for c in self.containers]
        self.controller.moreNavigationController.delegate = self.controller
        self.point('refresh_tabs')

    def new_navigation(self, content):
        self.point('navigation_' + str(len(self.created)))
        result = NS(tabBarItem=None)
        self.created.append(result)
        return result

    def addObserverForName(self, name, **kwargs):
        self.point('observer_' + str(len(self.observers)))
        token = object()
        self.observers.append(token)
        self.active.add(token)
        self.blocks.append(kwargs['usingBlock'])
        return token

    def removeObserver(self, token):
        self.removed.append(token)
        remaining = self.remove_failures.get(token, 0)
        if self.fail_remove or remaining:
            self.remove_failures[token] = max(0, remaining - 1)
            raise RuntimeError('remove sentinel')
        self.active.remove(token)

    def navigation_host(self):
        class Impl:
            __module__ = 'toga_iOS.optioncontainer'
        impl = Impl()
        impl.__dict__.update(vars(self.impl))
        self.host.root._impl = impl
        host = object.__new__(navigation.NativeNavigationHost)
        host.__dict__.update(vars(self.host))
        host.adapter = host.window = host._installing_adapter = None
        host.chrome.restore = Mock()
        self.host = host
        return host

    @contextmanager
    def installed(self):
        classes = {
            'NSNotificationCenter': NS(defaultCenter=self),
            'UINavigationController': NS(alloc=lambda: NS(initWithRootViewController=self.new_navigation)),
            'UIImage': NS(systemImageNamed=lambda symbol: self.image(symbol)),
            'UIDevice': NS(currentDevice=NS(userInterfaceIdiom=1)),
        }
        def objc_class(name):
            if name == 'NSNotificationCenter':
                self.point('center')
            return classes[name]
        def block(callback, *args):
            self.point('block_' + str(self.block_count))
            self.block_count += 1
            return callback
        objc = NS(ObjCClass=objc_class, SEL=lambda value: value,
                  Block=block, objc_id=object())
        with patch.dict(sys.modules, {'rubicon.objc': objc}):
            yield

    def image(self, symbol):
        self.point('image_' + symbol)
        return symbol


@unittest.skipUnless(HAS_TOGA, 'Apple constructor contracts require Toga')
class AppleConstructionTests(unittest.TestCase):
    def assert_retired(self, bridge, adapter):
        self.assertEqual(bridge.active, set())
        self.assert_inactive(bridge, adapter)

    def assert_inactive(self, bridge, adapter):
        self.assertFalse(adapter.keyboard_live)
        # Deliver already retained blocks and queued callbacks after failure.
        before = list(bridge.events)
        for block in bridge.blocks:
            block(object())
        adapter.layout_window(object())
        adapter.refresh_keyboard_focus()
        adapter.layout_keyboard()
        self.assertEqual(bridge.events, before)

    def test_each_observer_prefix_and_controller_entry_retires_returned_tokens(self):
        for failure in ['block_0', 'center', 'block_1', *(f'observer_{i}' for i in range(5)), 'controllers']:
            with self.subTest(failure=failure):
                bridge = Bridge(failure)
                adapter = object.__new__(navigation.AppleNavigation)
                install = (patch.object(navigation.AppleNavigation, '_install_controllers',
                           side_effect=bridge.error) if failure == 'controllers' else nullcontext())
                with bridge.installed(), install, self.assertRaises(RuntimeError) as caught:
                    adapter.__init__(bridge.host, bridge.window)
                self.assertIs(caught.exception, bridge.error)
                self.assert_retired(bridge, adapter)

    def test_success_uninstall_and_reinstall_after_observer_failure(self):
        bridge = Bridge('observer_2')
        host = bridge.navigation_host()
        with bridge.installed():
            with self.assertRaises(RuntimeError):
                host.install(bridge.window)
            self.assertIsNone(host.adapter)
            self.assertIsNone(host.window)
            self.assertFalse(host.changing)
            host.install(bridge.window)
            first = host.adapter
            self.assertTrue(first.keyboard_live)
            self.assertTrue(first.sidebar_used)
            self.assertFalse(host.changing)
            self.assertEqual(first.get_size(), (400, 800))
            with self.assertRaises(RuntimeError):
                host.install(bridge.window)
            host.uninstall()
            self.assertFalse(first.keyboard_live)
            self.assertIsNone(host.adapter)
            self.assertIsNone(host.window)
            self.assertIs(bridge.window._impl.get_size, bridge.original_get_size)
            host.install(bridge.window)
            self.assertIsNot(host.adapter, first)
            host.uninstall()

    def test_late_constructor_failure_restores_leaf_layout_and_retires_captured_callback(self):
        for failure in ('refresh_tabs', 'resize'):
            with self.subTest(failure=failure):
                bridge = Bridge(failure)
                frame = NS(origin=NS(x=0, y=0), size=NS(width=100, height=100))
                bounds = NS(origin=NS(x=0, y=0), size=NS(width=400, height=800))
                for container in bridge.containers:
                    container.native = NS(frame=frame, bounds=bounds,
                                          safeAreaInsets=NS(top=10, bottom=20, left=30, right=40))
                    container.content = NS(interface=NS(refresh=Mock()))
                original_navigation = bridge.new_navigation
                def new_navigation(content):
                    result = original_navigation(content)
                    result.navigationController = None
                    result.view = NS(bounds=bounds)
                    return result
                bridge.new_navigation = new_navigation
                original_refresh = bridge.impl.refresh_tabs
                retained = []
                def dispatch():
                    for container in bridge.containers:
                        container.on_native_layout(container)
                def refresh():
                    retained.extend(c.on_native_layout for c in bridge.containers)
                    dispatch()
                    original_refresh()
                def resize(container):
                    dispatch()
                    bridge.point('resize')
                bridge.impl.refresh_tabs = refresh
                bridge.window._impl.notify_resize = resize
                adapter = object.__new__(navigation.AppleNavigation)
                with bridge.installed(), self.assertRaises(RuntimeError):
                    adapter.__init__(bridge.host, bridge.window)
                self.assert_retired(bridge, adapter)
                for container, callback in zip(bridge.containers, retained):
                    self.assertEqual((container.top_inset, container.bottom_inset,
                                      container.left_inset, container.right_inset), (1, 2, 3, 4))
                    self.assertEqual(container.native.frame, frame)
                    self.assertEqual(container.content.interface.refresh.call_count,
                                     0 if failure == 'refresh_tabs' else 1)
                    container.content.interface.refresh.reset_mock()
                    callback(container)
                    container.content.interface.refresh.assert_not_called()

    def test_cleanup_failure_preserves_primary_error_and_attempts_every_observer(self):
        bridge = Bridge('controllers')
        bridge.fail_remove = True
        adapter = object.__new__(navigation.AppleNavigation)
        with bridge.installed(), patch.object(navigation.AppleNavigation, '_install_controllers', side_effect=bridge.error):
            with self.assertRaises(RuntimeError) as caught:
                adapter.__init__(bridge.host, bridge.window)
        self.assertIs(caught.exception, bridge.error)
        self.assert_inactive(bridge, adapter)
        self.assertCountEqual(bridge.removed, bridge.observers)
        self.assertEqual(bridge.active, set(bridge.observers))
        self.assertIs(bridge.host._installing_adapter, adapter)
        self.assertTrue(caught.exception.__notes__)
        bridge.fail_remove = False
        adapter._rollback_construction()
        self.assert_retired(bridge, adapter)

    def test_constructor_failure_prefixes_restore_owned_bindings(self):
        for failure in ('outer_bar', 'containment', 'did_move', 'tabs', 'navigation_0',
                        'image_house', 'navigation_1', 'image_doc', 'refresh_tabs', 'mode', 'resize'):
            with self.subTest(failure=failure):
                bridge = Bridge(failure)
                adapter = object.__new__(navigation.AppleNavigation)
                with bridge.installed(), self.assertRaises(RuntimeError) as caught:
                    adapter.__init__(bridge.host, bridge.window)
                self.assertIs(caught.exception, bridge.error)
                self.assert_retired(bridge, adapter)
                self.assertIs(bridge.root_container.on_native_layout, bridge.original_layout)
                self.assertIs(bridge.window._impl.get_size, bridge.original_get_size)
                self.assertEqual(tuple(getattr(bridge.root_container, n + '_inset') for n in ('top','bottom','left','right')), (1,2,3,4))
                self.assertFalse(bridge.outer.hidden)
                self.assertIsNone(bridge.controller.parentViewController)
                self.assertEqual(bridge.controller.viewControllers, bridge.contents)
                self.assertEqual(bridge.controller.mode, 0)
                for i, container in enumerate(bridge.containers):
                    self.assertIs(container.controller, bridge.contents[i])
                    self.assertIs(container.on_native_layout, bridge.original_callbacks[i])
                    self.assertEqual(bridge.contents[i].title, 'Original ' + str(i))
                    self.assertIs(bridge.contents[i].tabBarItem.image, bridge.original_images[i])

    def test_observer_retirement_retains_only_failed_tokens_for_retry(self):
        bridge = Bridge()
        adapter = object.__new__(navigation.AppleNavigation)
        adapter.notification_center = bridge
        adapter.keyboard_live = True
        keyboard, first, second = object(), object(), object()
        adapter.keyboard_observer = keyboard
        adapter.keyboard_focus_observers = [first, second]
        bridge.active.update((keyboard, first, second))
        bridge.remove_failures = {keyboard: 1, second: 1}
        with self.assertRaises(ExceptionGroup):
            adapter._retire_keyboard_observers()
        self.assertFalse(adapter.keyboard_live)
        self.assertEqual(bridge.active, {keyboard, second})
        self.assertEqual(bridge.removed, [keyboard, first, second])
        self.assertIs(adapter.keyboard_observer, keyboard)
        self.assertEqual(adapter.keyboard_focus_observers, [second])
        adapter._retire_keyboard_observers()
        self.assertEqual(bridge.active, set())
        self.assertIsNone(adapter.keyboard_observer)
        self.assertEqual(adapter.keyboard_focus_observers, [])
        self.assertEqual(bridge.removed, [keyboard, first, second, keyboard, second])
        adapter._retire_keyboard_observers()
        self.assertEqual(len(bridge.removed), 5)

    def test_normal_uninstall_retries_native_removal_without_forgetting_owner(self):
        bridge = Bridge()
        host = bridge.navigation_host()
        with bridge.installed():
            host.install(bridge.window)
            adapter = host.adapter
            keyboard, focus = bridge.observers[0], bridge.observers[3]
            bridge.remove_failures = {keyboard: 1, focus: 1}
            with self.assertRaises(ExceptionGroup):
                host.uninstall()
            self.assertIs(host.adapter, adapter)
            self.assertIs(host.window, bridge.window)
            self.assertEqual(bridge.active, {keyboard, focus})
            self.assert_inactive(bridge, adapter)
            with self.assertRaises(RuntimeError):
                host.install(bridge.window)
            host.uninstall()
            self.assertIsNone(host.adapter)
            self.assertIsNone(host.window)
            self.assertEqual(bridge.active, set())
            self.assertEqual(bridge.removed, bridge.observers + [keyboard, focus])

    def test_failed_constructor_retains_draft_until_uninstall_can_finish(self):
        bridge = Bridge('navigation_1')
        bridge.fail_remove = True
        host = bridge.navigation_host()
        with bridge.installed():
            with self.assertRaises(RuntimeError) as caught:
                host.install(bridge.window)
            self.assertIs(caught.exception, bridge.error)
            adapter = host._installing_adapter
            self.assertIsNotNone(adapter)
            self.assertIsNone(host.adapter)
            self.assertIs(host.window, bridge.window)
            self.assert_inactive(bridge, adapter)
            self.assertEqual(bridge.active, set(bridge.observers))
            with self.assertRaisesRegex(RuntimeError, 'cleanup is pending'):
                host.install(bridge.window)
            with self.assertRaises(ExceptionGroup):
                host.uninstall()
            self.assertIs(host._installing_adapter, adapter)
            bridge.fail_remove = False
            host.uninstall()
            self.assertIsNone(host._installing_adapter)
            self.assertIsNone(host.window)
            self.assert_retired(bridge, adapter)
            host.install(bridge.window)
            self.assertTrue(host.adapter.keyboard_live)
            host.uninstall()

    def test_cleanup_getter_error_cannot_replace_constructor_error(self):
        bridge = Bridge('resize')
        broken = [False]
        class Controller(NS):
            def __getattribute__(self, name):
                if name == 'moreNavigationController' and broken[0]:
                    raise LookupError('More getter sentinel')
                return super().__getattribute__(name)
        bridge.controller = Controller(**vars(bridge.controller))
        bridge.impl.native_controller = bridge.controller
        original_resize = bridge.window._impl.notify_resize
        def resize(container):
            broken[0] = True
            original_resize(container)
        bridge.window._impl.notify_resize = resize
        host = bridge.navigation_host()
        with bridge.installed():
            with self.assertRaises(RuntimeError) as caught:
                host.install(bridge.window)
            self.assertIs(caught.exception, bridge.error)
            self.assertIsNotNone(host._installing_adapter)
            self.assertIsNot(bridge.root_container.on_native_layout, bridge.original_layout)
            for container, callback in zip(bridge.containers, bridge.original_callbacks):
                self.assertIsNot(container.on_native_layout, callback)
                container.on_native_layout(object())  # Gated before any native access.
            broken[0] = False
            host.uninstall()
            self.assertIsNone(host._installing_adapter)
            self.assertEqual(bridge.active, set())

    def test_failed_install_preserves_existing_parent_and_more_stack(self):
        bridge = Bridge('resize')
        bridge.controller.parentViewController = bridge.parent
        more = bridge.controller.moreNavigationController
        stack, delegate = list(more.viewControllers), more.delegate
        bridge.controller.selectedViewController = more
        original_resize = bridge.window._impl.notify_resize
        def resize(container):
            more.viewControllers = [object()]
            original_resize(container)
        bridge.window._impl.notify_resize = resize
        host = bridge.navigation_host()
        with bridge.installed(), self.assertRaises(RuntimeError):
            host.install(bridge.window)
        self.assertIs(bridge.controller.parentViewController, bridge.parent)
        self.assertEqual(more.viewControllers, stack)
        self.assertIs(more.delegate, delegate)
        self.assertIs(bridge.controller.selectedViewController, more)
        self.assertIsNone(host._installing_adapter)
        self.assertIsNone(host.window)

    def test_unknown_replacement_more_owner_keeps_cleanup_pending(self):
        bridge = Bridge('resize')
        original_more = bridge.controller.moreNavigationController
        original_resize = bridge.window._impl.notify_resize
        def resize(container):
            bridge.controller.moreNavigationController = NS()
            original_resize(container)
        bridge.window._impl.notify_resize = resize
        host = bridge.navigation_host()
        with bridge.installed():
            with self.assertRaises(RuntimeError) as caught:
                host.install(bridge.window)
            self.assertIs(caught.exception, bridge.error)
            self.assertIsNotNone(host._installing_adapter)
            with self.assertRaises(ExceptionGroup):
                host.uninstall()
            bridge.controller.moreNavigationController = original_more
            host.uninstall()
            self.assertIsNone(host._installing_adapter)
            self.assertIsNone(host.window)

    def test_static_layout_extension_keeps_one_argument_and_native_dispatch_is_gated(self):
        bridge = Bridge()
        host = bridge.navigation_host()
        leaf_hook, window_hook = Mock(), Mock()
        with bridge.installed(), \
                patch.object(navigation.AppleNavigation, 'layout_content', new=staticmethod(leaf_hook)), \
                patch.object(navigation.AppleNavigation, 'layout_window', new=window_hook):
            host.install(bridge.window)
            adapter = host.adapter
            leaf = bridge.containers[0]
            callback, window_callback = leaf.on_native_layout, bridge.root_container.on_native_layout
            callback(leaf)
            leaf_hook.assert_called_once_with(leaf)
            # The established direct static hook remains callable by consumer wrappers.
            navigation.AppleNavigation.layout_content(leaf)
            window_callback(bridge.root_container)
            self.assertEqual(window_hook.call_count, 2)
            host.uninstall()
            leaf_hook.reset_mock()
            window_hook.reset_mock()
            callback(object())
            window_callback(object())
            leaf_hook.assert_not_called()
            window_hook.assert_not_called()
            self.assertEqual(adapter.get_size(), (400, 800))
            bridge.original_get_size.assert_called_once_with()

    def test_extended_constructor_failure_keeps_completed_base_until_disposal_succeeds(self):
        for failed_removal in (False, True):
            with self.subTest(failed_removal=failed_removal):
                bridge = Bridge()
                host = bridge.navigation_host()
                error = LookupError('consumer extension sentinel')
                initialize = navigation.AppleNavigation.__init__
                dispose = navigation.AppleNavigation.dispose
                disposed = []
                def extended_init(adapter, host, window):
                    initialize(adapter, host, window)
                    bridge.fail_remove = failed_removal
                    raise error
                def extended_dispose(adapter):
                    disposed.append(adapter)
                    dispose(adapter)
                with bridge.installed(), \
                        patch.object(navigation.AppleNavigation, '__init__', extended_init), \
                        patch.object(navigation.AppleNavigation, 'dispose', extended_dispose):
                    with self.assertRaises(LookupError) as caught:
                        host.install(bridge.window)
                    self.assertIs(caught.exception, error)
                    self.assertIsNone(host.adapter)
                    self.assertEqual(len(disposed), 1)
                    if failed_removal:
                        self.assertIs(host._installing_adapter, disposed[0])
                        self.assertEqual(bridge.active, set(bridge.observers))
                        bridge.fail_remove = False
                        host.uninstall()
                        self.assertEqual(len(disposed), 2)
                    self.assertIsNone(host._installing_adapter)
                    self.assertIsNone(host.window)
                    self.assertEqual(bridge.active, set())
                    self.assertIs(bridge.root_container.on_native_layout, bridge.original_layout)
                    self.assertEqual(bridge.controller.mode, 0)

    def test_foreign_parent_is_rejected_without_mutating_its_containment(self):
        bridge = Bridge()
        other = object()
        bridge.controller.parentViewController = other
        host = bridge.navigation_host()
        with bridge.installed(), self.assertRaisesRegex(ValueError, 'another parent'):
            host.install(bridge.window)
        self.assertIs(bridge.controller.parentViewController, other)
        self.assertEqual(bridge.active, set())
        self.assertFalse(bridge.outer.hidden)
        self.assertIs(bridge.root_container.on_native_layout, bridge.original_layout)
        self.assertIsNone(host._installing_adapter)
        self.assertIsNone(host.window)

    def test_initial_resize_cannot_publish_a_draft_retired_by_its_callback(self):
        bridge = Bridge()
        host = bridge.navigation_host()
        def resize(container):
            host.uninstall()
            with self.assertRaisesRegex(RuntimeError, 'installation is in progress'):
                host.install(bridge.window)
        bridge.window._impl.notify_resize = resize
        with bridge.installed():
            with self.assertRaisesRegex(RuntimeError, 'retired during'):
                host.install(bridge.window)
            self.assertIsNone(host.adapter)
            self.assertIsNone(host._installing_adapter)
            self.assertIsNone(host.window)
            self.assertEqual(bridge.active, set())
            bridge.window._impl.notify_resize = lambda container: bridge.point('resize')
            host.install(bridge.window)
            self.assertTrue(host.adapter.keyboard_live)
            host.uninstall()
