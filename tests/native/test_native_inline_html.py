"""Inline origin adaptation preserves document identity and existing view validation."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from commonUtils.ui.native.inline_html import set_inline_html


class InlineHtmlTests(unittest.TestCase):
    def view(self, backend):
        base = type('Backend', (), {'__module__': backend})
        private = type('PrivateBackend', (base,), {'__module__': 'consumer.private'})
        return SimpleNamespace(_impl=private(), set_content=Mock())

    def test_private_apple_view_keeps_identity_and_html(self):
        view = self.view('toga_iOS.widgets.webview')
        html = '<p>Private document</p>'
        set_inline_html(view, 'https://reader.invalid/A%2fB/?id=A%2BB#Heading', html)
        view.set_content.assert_called_once_with('app-document://reader.invalid/A%2fB/?id=A%2BB#Heading', html)

    def test_android_keeps_its_existing_content_origin(self):
        view = self.view('toga_android.widgets.webview')
        set_inline_html(view, 'https://reader.invalid/page/', '<p>Text</p>')
        view.set_content.assert_called_once_with('https://reader.invalid/page/', '<p>Text</p>')

    def test_actual_web_origins_and_blank_are_unchanged(self):
        for root in ('https://example.com/page/', None, 'about:blank'):
            with self.subTest(root=root):
                view = self.view('toga_iOS.widgets.webview')
                set_inline_html(view, root, '<p>Text</p>')
                view.set_content.assert_called_once_with(root, '<p>Text</p>')

    def test_view_validation_failure_is_preserved(self):
        view = self.view('toga_iOS.widgets.webview')
        view.set_content.side_effect = RuntimeError('Private view is closed or unprotected.')
        with self.assertRaisesRegex(RuntimeError, 'closed or unprotected'):
            set_inline_html(view, 'https://reader.invalid/page/', '<p>Text</p>')
