"""Native owner lifetime contracts with dummy/fake adapters, not device evidence."""
import asyncio
from importlib.util import find_spec
import os
import gc
import sys
import weakref
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('TOGA_BACKEND', 'toga_dummy')
HAS_TOGA = find_spec('toga') is not None
if HAS_TOGA:
    import toga
    from commonUtils.ui.native import navigation
    from commonUtils.ui.native.image_canvas import ImageCanvas
    from commonUtils.ui.native.speech import NativeSpeech


@unittest.skipUnless(HAS_TOGA, 'Native owner contracts require Toga')
class NativeOwnerLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = toga.App('Owner contracts', 'org.example.ownercontracts')

    def test_six_destinations_retain_order_and_seventh_is_selectable(self):
        items = tuple((str(i), 'Page ' + str(i), 'doc', 'ic_menu_edit') for i in range(7))
        host = navigation.NativeNavigationHost(items)
        self.assertEqual([item.text for item in host.root.content], [item[1] for item in items])
        host.activate('6')
        self.assertEqual(host.root.current_tab.text, 'Page 6')
        self.assertEqual(host.state.destination, '6')
        with self.assertRaises(ValueError):
            navigation.NativeNavigationHost(items + (('8', 'Eight', 'doc', 'ic_menu_edit'),))

    def test_apple_overflow_resolves_the_actual_navigation_and_route_depth(self):
        from types import SimpleNamespace as NS
        adapter = object.__new__(navigation.AppleNavigation)
        own = NS(topViewController=None)
        more = NS(topViewController='Settings content', viewControllers=['More list', 'Settings content', 'Detail'])
        root = NS(navigationController=more)
        more.viewControllers = ['More list', root, 'Detail']
        adapter.host = NS(destinations=('home', 'settings'), state=NS(destination='settings'))
        adapter.containers = [(None, NS(navigationController=None)), (None, root)]
        adapter.navigation = [NS(topViewController='Home'), own]
        adapter.controller = NS(moreNavigationController=more)
        self.assertTrue(adapter.is_destination_controller(root))
        self.assertFalse(adapter.is_destination_controller(object()))
        self.assertIs(adapter.navigation_for('settings'), more)
        self.assertEqual(adapter.content_controller('settings'), 'Settings content')
        self.assertEqual(adapter.destination_for_navigation(more), 'settings')
        self.assertEqual(adapter.route_depth(more), 1)
        more.viewControllers = ['More list']
        self.assertIsNone(adapter.destination_for_navigation(more))
        root.navigationController = None
        self.assertIs(adapter.navigation_for('settings'), own)
        self.assertIs(adapter.content_controller('settings'), root)

    def test_programmatic_overflow_callback_does_not_reselect_or_cancel_routes(self):
        selected = Mock()
        items = tuple((str(i), 'Page ' + str(i), 'doc', 'ic_menu_edit') for i in range(6))
        host = navigation.NativeNavigationHost(items, on_select=selected)
        host.activate('5')
        host._programmatic_overflow = '5'
        host._selected(host.root)
        selected.assert_not_called()
        self.assertIsNone(host._programmatic_overflow)
        host._selected(host.root)
        selected.assert_called_once_with('5')
        with patch.object(host.root._impl, 'set_current_tab_index', wraps=host.root._impl.set_current_tab_index) as setter:
            host.activate('5')
        setter.assert_not_called()
        host._programmatic_overflow = '5'
        host.activate('2')
        self.assertIsNone(host._programmatic_overflow)

    def test_navigation_reinstall_preserves_selection_and_restores_before_detaching(self):
        selected = Mock()
        host = navigation.NativeNavigationHost((
            ('home', 'Home', 'house', 'home'), ('notes', 'Notes', 'doc', 'ic_menu_edit'),
        ), on_select=selected)
        host.activate('notes')
        events = []
        adapters = [Mock(), Mock()]
        for index, adapter in enumerate(adapters):
            adapter.dispose.side_effect = lambda i=index: events.append(('dispose', i))
        with patch.object(type(host.root._impl), '__module__', 'toga_iOS.optioncontainer'), \
                patch.object(navigation, 'AppleNavigation', side_effect=adapters) as factory, \
                patch.object(host.chrome, 'restore', side_effect=lambda: events.append('restore')):
            first, second = object(), object()
            host.install(first)
            with self.assertRaises(RuntimeError):
                host.install(first)
            self.assertEqual(factory.call_count, 1)
            host.uninstall()
            host.uninstall()
            self.assertIsNone(host.window)
            self.assertIsNone(host.adapter)
            host.install(second)
            self.assertIs(host.adapter, adapters[1])
            self.assertEqual(host.state.destination, 'notes')
            host.uninstall()
        self.assertEqual(events, ['restore', ('dispose', 0), 'restore', 'restore', ('dispose', 1)])
        selected.assert_not_called()
        host.dispose()
        self.assertIsNone(host.on_select)

    def test_canvas_disposal_detaches_each_backend_and_rejects_old_page_actions(self):
        for backend in ('apple', 'android'):
            with self.subTest(backend=backend):
                page, toggle, magnify = Mock(), Mock(), Mock()
                canvas = ImageCanvas(on_page=page, on_toggle=toggle, on_magnifier_zoom=magnify,
                                     magnifier_enabled=True)
                native = SimpleNamespace(delegate=object(), userInteractionEnabled=True,
                                         setPageListener=Mock())
                field = 'picture' if backend == 'apple' else 'listener'
                with patch.object(canvas._impl, field, object(), create=True), \
                        patch.object(canvas._impl, 'native', native, create=True):
                    canvas.dispose()
                    canvas.dispose()
                    if backend == 'apple':
                        self.assertIsNone(native.delegate)
                        self.assertFalse(native.userInteractionEnabled)
                    else:
                        self.assertIsNone(canvas._impl.listener)
                        self.assertTrue(native.setPageListener.called)
                        self.assertTrue(all(call.args == (None,) for call in native.setPageListener.call_args_list))
                canvas.page(1)
                canvas.toggle_controls()
                self.assertFalse(canvas.magnifier_enabled)
                self.assertIsNone(canvas.on_magnifier_zoom)
                self.assertIsNone(canvas.image)
                page.assert_not_called()
                toggle.assert_not_called()
                magnify.assert_not_called()

    def test_failed_navigation_install_can_be_retried(self):
        host = navigation.NativeNavigationHost((('home', 'Home', 'house', 'home'),))
        adapter = Mock()
        with patch.object(type(host.root._impl), '__module__', 'toga_iOS.optioncontainer'), \
                patch.object(navigation, 'AppleNavigation', side_effect=[ValueError('admission'), adapter]):
            with self.assertRaisesRegex(ValueError, 'admission'):
                host.install(object())
            self.assertIsNone(host.window)
            self.assertIsNone(host.adapter)
            window = object()
            host.install(window)
            self.assertIs(host.window, window)
            host.uninstall()

    def test_retired_navigation_callbacks_do_not_touch_native_objects(self):
        apple = object.__new__(navigation.AppleNavigation)
        apple.keyboard_live = False
        apple.layout_window(object())
        android = object.__new__(navigation.AndroidNavigation)
        android.active = False
        android.window_resized(object())
        android.resize_content()
        android.content_refreshed()

    def test_android_rejects_missing_window_before_mutating_controls(self):
        host = SimpleNamespace(root=SimpleNamespace(_impl=Mock(), _MIN_HEIGHT=100))
        modules = {'android': SimpleNamespace(R=object()),
                   'com.google.android.material.navigation': SimpleNamespace(NavigationBarView=object()),
                   'java': SimpleNamespace(dynamic_proxy=Mock())}
        with patch.dict(sys.modules, modules), self.assertRaises(AttributeError):
            navigation.AndroidNavigation(host, object())
        self.assertEqual(host.root._MIN_HEIGHT, 100)
        host.root._impl.rehint.assert_not_called()

    def test_android_forwards_resize_to_the_already_bound_toga_handler(self):
        from toga.handlers import wrapped_handler
        window, handler = object(), Mock()
        adapter = object.__new__(navigation.AndroidNavigation)
        adapter.active, adapter.layout_events = True, 0
        adapter.old_window_resize = wrapped_handler(window, handler)
        adapter.update_keyboard_inset = Mock()
        adapter.impl = SimpleNamespace(native=SimpleNamespace(getWidth=lambda: 400), scale_out=lambda value: value)
        adapter.set_mode = Mock()
        adapter.window_resized(window)
        handler.assert_called_once_with(window)

    def test_android_native_selection_is_programmatic_during_install_and_restoration(self):
        adapter = object.__new__(navigation.AndroidNavigation)
        adapter.host = SimpleNamespace(changing=False, destinations=('home', 'notes'),
                                       state=SimpleNamespace(destination='notes'))
        def select(index):
            self.assertEqual(index, 1)
            self.assertTrue(adapter.host.changing)
        adapter.impl = SimpleNamespace(set_current_tab_index=select)
        adapter.select_current_tab()
        self.assertFalse(adapter.host.changing)
        adapter.host.changing = True
        adapter.select_current_tab()
        self.assertTrue(adapter.host.changing)

    def test_speech_close_releases_presentation_owners_even_when_native_stop_fails(self):
        class Receiver:
            def callback(self, *args):
                pass

        for broken_stop in (False, True):
            with self.subTest(broken_stop=broken_stop):
                loop = asyncio.new_event_loop()
                try:
                    engine = NativeSpeech(loop)
                    receiver = Receiver()
                    reference = weakref.ref(receiver)
                    engine.completed = engine.failed = engine.progress = engine.started = receiver.callback
                    engine.ready = True
                    del receiver
                    with patch.object(engine, 'stop', side_effect=RuntimeError('native') if broken_stop else None):
                        if broken_stop:
                            with self.assertRaisesRegex(RuntimeError, 'native'):
                                engine.close()
                        else:
                            engine.close()
                    gc.collect()
                    self.assertIsNone(reference())
                    self.assertFalse(engine.ready)
                finally:
                    loop.close()

    def test_speech_close_detaches_once_and_suppresses_already_queued_deliveries(self):
        for backend in ('toga_android.speech', 'toga_iOS.speech'):
            with self.subTest(backend=backend):
                loop = asyncio.new_event_loop()
                try:
                    engine = NativeSpeech(loop)
                    engine.backend, engine.native = backend, Mock()
                    engine.progress_listener = Mock()
                    engine.voices, engine.ready = {'Offline': object()}, True
                    engine.utterance = object()
                    callbacks = [Mock() for _ in range(4)]
                    engine.completed, engine.failed, engine.progress, engine.started = callbacks
                    def deliver():
                        engine.deliver('token')
                        engine.failure('token')
                        engine.word_range('token', 0, 3)
                        engine.begin('token')
                    deliver()
                    engine.close()
                    engine.close()
                    deliver()
                    loop.run_until_complete(asyncio.sleep(0))
                    for callback in callbacks:
                        callback.assert_not_called()
                    self.assertEqual(engine.voices, {})
                    if backend.startswith('toga_android.'):
                        engine.progress_listener.detach.assert_called_once_with()
                        engine.native.stop.assert_called_once_with()
                        engine.native.shutdown.assert_called_once_with()
                    else:
                        self.assertIsNone(engine.native.delegate)
                        self.assertIsNone(engine.utterance)
                        engine.native.stopSpeakingAtBoundary.assert_called_once_with(0)
                    with self.assertRaises(RuntimeError):
                        engine.speak('Late text', 'Offline', 1, 'late')
                finally:
                    loop.close()
