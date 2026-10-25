"""Private HTML must bypass the toolkit's disk cache even above 2 MiB."""
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
            'https://private.invalid/', content, 'text/html', 'utf-8', None)
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
