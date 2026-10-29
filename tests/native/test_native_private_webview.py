"""Private HTML must bypass the toolkit's disk cache even above 2 MiB."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from importlib.util import find_spec
import os
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('TOGA_BACKEND', 'toga_dummy')
HAS_TOGA = find_spec('toga') is not None
if HAS_TOGA:
    from commonUtils.ui.native.private_webview import PrivateWebView


@unittest.skipUnless(HAS_TOGA, 'Private WebView contracts require Toga')
class PrivateWebViewTests(unittest.TestCase):
    def test_android_large_html_uses_native_memory_loader_and_private_settings(self):
        class Backend:
            __module__ = 'toga_android.widgets.webview'
            def __init__(self, *, interface):
                self.interface = interface
                self.create()
            def create(self):
                self.settings, self.native = Mock(), Mock()
            def set_content(self, *args):
                raise AssertionError('Public large-content cache entered')
        module = ModuleType('toga_android.widgets.webview')
        module.WebView = Backend
        android = ModuleType('android.webkit')
        android.WebView = Mock()
        android.WebSettings = SimpleNamespace(LOAD_NO_CACHE=-1)
        interface = SimpleNamespace(factory=SimpleNamespace(WebView=Backend))
        with patch.dict(sys.modules, {'toga_android.widgets.webview': module, 'android.webkit': android}):
            backend = PrivateWebView._create(interface)
        content = '<p>private sentinel</p>' + '<!--' + 'x' * (3 * 1024 * 1024) + '-->'
        backend.set_content('https://private.invalid/', content)
        backend.native.loadDataWithBaseURL.assert_called_once_with(
            'https://private.invalid/', content, 'text/html', 'utf-8', 'https://private.invalid/')
        backend.native.loadUrl.assert_not_called()
        backend.native.loadData.assert_not_called()
        backend.settings.setDomStorageEnabled.assert_called_once_with(False)
        backend.settings.setDatabaseEnabled.assert_called_once_with(False)
        backend.settings.setSaveFormData.assert_called_once_with(False)
        backend.settings.setCacheMode.assert_called_once_with(-1)
        backend.settings.setAllowFileAccess.assert_called_once_with(False)
        backend.settings.setAllowContentAccess.assert_called_once_with(False)
        self.assertTrue(interface.private_configured)

    def test_byte_limit_counts_utf8_before_native_io(self):
        view = object.__new__(PrivateWebView)
        view.private_closed, view.private_configured = False, True
        view.max_html_bytes = 4
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            view.set_content('https://private.invalid/', 'ééé')

    def test_closed_or_unprotected_views_reject_content(self):
        view = object.__new__(PrivateWebView)
        view.private_closed, view.private_configured = True, True
        with self.assertRaisesRegex(RuntimeError, 'closed or unprotected'):
            view.set_content('', 'secret')
        view.private_closed, view.private_configured = False, False
        with self.assertRaisesRegex(RuntimeError, 'closed or unprotected'):
            view.set_content('', 'secret')


@unittest.skipUnless(HAS_TOGA, 'Private WebView contracts require Toga')
class PrivateLoadCompletionTests(unittest.IsolatedAsyncioTestCase):
    def test_native_blank_completion_waits_for_current_memory_document(self):
        backend = type('Backend', (), {'__module__': 'toga_android.widgets.webview'})
        view = object.__new__(PrivateWebView)
        view.factory = SimpleNamespace(WebView=backend)
        view._impl = SimpleNamespace(SUPPORTS_ON_WEBVIEW_LOAD=True)
        view.private_closed, view._private_content_ready = False, False
        callback = Mock()
        view.on_webview_load = callback
        view.on_webview_load()
        callback.assert_not_called()
        view._private_content_ready = True
        view.on_webview_load()
        callback.assert_called_once_with(view)

    async def test_only_the_marked_complete_document_dispatches_completion(self):
        import asyncio
        from unittest.mock import AsyncMock
        view = SimpleNamespace(private_closed=False, _private_load_token='current',
            evaluate_javascript=AsyncMock(side_effect=[False, True]), on_webview_load=Mock())
        task = view._private_load_task = asyncio.create_task(PrivateWebView._finish_private_load(view, 'current'))
        await task
        view.on_webview_load.assert_called_once_with()
        self.assertIsNone(view._private_load_task)
        self.assertIn('private-load:current', view.evaluate_javascript.call_args.args[0])

    async def test_replaced_document_cannot_publish_an_inflight_completion(self):
        import asyncio
        entered, released = asyncio.Event(), asyncio.Event()
        async def evaluate(script):
            entered.set()
            await released.wait()
            return True
        view = SimpleNamespace(private_closed=False, _private_load_token='old',
            evaluate_javascript=evaluate, on_webview_load=Mock())
        task = view._private_load_task = asyncio.create_task(PrivateWebView._finish_private_load(view, 'old'))
        await entered.wait()
        view._private_load_token = 'new'
        released.set()
        await task
        view.on_webview_load.assert_not_called()

    async def test_disposal_cancels_the_owned_completion_task(self):
        import asyncio
        from unittest.mock import AsyncMock
        view = SimpleNamespace(private_closed=False, _private_load_token='current',
            evaluate_javascript=AsyncMock(return_value=False), on_webview_load=Mock())
        task = view._private_load_task = asyncio.create_task(PrivateWebView._finish_private_load(view, 'current'))
        await asyncio.sleep(0)
        view.private_closed = True
        PrivateWebView._cancel_private_load(view)
        with self.assertRaises(asyncio.CancelledError):
            await task
        view.on_webview_load.assert_not_called()
        self.assertIsNone(view._private_load_task)

    async def test_disposal_does_not_cancel_the_native_javascript_result(self):
        import asyncio
        entered = asyncio.Event()
        native_result = asyncio.get_running_loop().create_future()
        def evaluate(script):
            entered.set()
            return native_result
        view = SimpleNamespace(private_closed=False, _private_load_token='current',
            evaluate_javascript=evaluate, on_webview_load=Mock())
        task = view._private_load_task = asyncio.create_task(PrivateWebView._finish_private_load(view, 'current'))
        await entered.wait()
        view.private_closed = True
        PrivateWebView._cancel_private_load(view)
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(native_result.cancelled())
        native_result.set_result(True)
        view.on_webview_load.assert_not_called()
