"""Reusable private WebViews; content stays in RAM, never Toga's file cache.

Toolkit adapters are selected by the active backend, not the host OS. Unsupported
backends use the native text fallback rather than an ordinary persistent WebView.
"""

import toga
from toga.platform import get_factory

DEFAULT_MAX_HTML = 2 * 1024 * 1024


def private_webview_supported():
    return get_factory().WebView.__module__.startswith(("toga_iOS.", "toga_android."))


class PrivateWebView(toga.WebView):
    def __init__(self, *args, max_html_bytes=DEFAULT_MAX_HTML, **kwargs):
        if type(max_html_bytes) is not int or max_html_bytes <= 0:
            raise ValueError("Private HTML byte limit must be positive.")
        self.max_html_bytes = max_html_bytes
        super().__init__(*args, **kwargs)

    def _create(self):
        backend = self.factory.WebView.__module__
        self.private_closed = False
        self.private_configured = False
        if backend.startswith("toga_iOS."):
            from rubicon.objc import ObjCClass, CGRect
            from toga_iOS.widgets.webview import WebView, TogaWebView

            class PrivateBackend(WebView):
                def create(inner):
                    configuration = ObjCClass("WKWebViewConfiguration").alloc().init()
                    store = ObjCClass("WKWebsiteDataStore").nonPersistentDataStore()
                    configuration.websiteDataStore = store
                    inner.native = TogaWebView.alloc().initWithFrame(
                        CGRect((0, 0), (0, 0)), configuration=configuration
                    )
                    inner.native.interface, inner.native.impl = inner.interface, inner
                    inner.native.navigationDelegate = inner.native
                    inner.native.UIDelegate = inner.native
                    try:
                        inner.native.inspectable = False
                    except AttributeError:
                        pass
                    inner.loaded_future, inner._allowed_url = None, None
                    inner.add_constraints()
                    if bool(store.isPersistent()):
                        raise RuntimeError(
                            "Private view requires a nonpersistent WebView store."
                        )
                    inner.interface.private_configured = True

            return PrivateBackend(interface=self)
        if backend.startswith("toga_android."):
            from toga_android.widgets.webview import WebView
            from android.webkit import WebView as NativeWebView, WebSettings

            class PrivateBackend(WebView):
                def create(inner):
                    super().create()
                    inner.settings.setDomStorageEnabled(False)
                    inner.settings.setDatabaseEnabled(False)
                    inner.settings.setSaveFormData(False)
                    inner.settings.setCacheMode(WebSettings.LOAD_NO_CACHE)
                    inner.settings.setAllowFileAccess(False)
                    inner.settings.setAllowContentAccess(False)
                    NativeWebView.setWebContentsDebuggingEnabled(False)
                    inner.interface.private_configured = True

                def set_content(inner, root_url, content):
                    # Toga's large-content path writes HTML to its cache. Keep
                    # private documents in WebView memory, including custom
                    # limits above its 2 MiB data-URL threshold.
                    inner.loaded_future = None
                    inner.native.loadDataWithBaseURL(root_url, content, "text/html", "utf-8", None)

            return PrivateBackend(interface=self)
        raise RuntimeError("This backend does not support a private WebView.")

    def set_content(self, root_url, content):
        if self.private_closed or not self.private_configured:
            raise RuntimeError("Private view is closed or unprotected.")
        # Enforce the caller's byte bound before crossing the native boundary.
        # Android's private backend bypasses Toga's disk-backed HTML fallback.
        if len(content.encode("utf-8")) > getattr(
            self, "max_html_bytes", DEFAULT_MAX_HTML
        ):
            raise ValueError("Private HTML exceeds the memory-only byte limit.")
        return super().set_content(root_url, content)

    def clear_private_content(self):
        if self.private_closed:
            return
        self.private_closed = True
        self.on_webview_load = None
        self.on_navigation_starting = lambda widget, url, **kw: False
        native = self._impl.native
        native.stopLoading()
        if self.factory.WebView.__module__.startswith("toga_iOS."):
            native.navigationDelegate = None
            native.UIDelegate = None
            # A hidden WKWebView may defer the blank navigation. Remove its
            # live document first, independently of the next rendered page.
            native.evaluateJavaScript(
                'document.open();document.write("");document.close();',
                completionHandler=None,
            )
            native.loadHTMLString("", baseURL=None)
        else:
            native.loadData("", "text/html", "utf-8")
            native.clearHistory()
            native.removeAllViews()
            native.destroy()
