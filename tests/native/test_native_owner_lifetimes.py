"""Native owner lifetime contracts with dummy/fake adapters, not device evidence."""
import asyncio
from importlib.util import find_spec
import os
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
