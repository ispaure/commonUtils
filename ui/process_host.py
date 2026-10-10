"""Optional application-owned process workspace; standalone callers stay native."""
import weakref
from shiboken6 import isValid
from . import pyside as qt


def register_process_host(host):
    qt.QApplication.instance()._commonutils_process_host = weakref.ref(host)


def show_process(window):
    application = qt.QApplication.instance()
    reference = getattr(application, '_commonutils_process_host', None)
    host = reference() if reference else None
    if host is not None and isValid(host) and host.window().isVisible() and not host.closing:
        host.present(window)
    else:
        window.show()
