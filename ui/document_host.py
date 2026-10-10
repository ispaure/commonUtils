"""Optional application document host; standalone consumers need no registration."""
import weakref
from . import pyside as qt
from shiboken6 import isValid


def register_document_host(host):
    qt.QApplication.instance()._commonutils_document_host = weakref.ref(host)


def current_document_host():
    app = qt.QApplication.instance()
    reference = getattr(app, '_commonutils_document_host', None)
    host = reference() if reference else None
    return host if host is not None and isValid(host) else None


def show_document(window):
    host = current_document_host()
    if host is not None and host.window().isVisible() and not host.closing:
        host.present(window)
    else:
        window.showNormal() if window.isMinimized() else window.show()
        window.raise_()
        window.activateWindow()
    return window


def document_is_open(window):
    if not isValid(window):
        return False
    host = current_document_host()
    if host is not None and window in host.records:
        return not host.records[window]['closed']
    return window.isVisible()


def host_keeps_document(window):
    """An origin view may close while the main host retains its document."""
    host = current_document_host()
    return bool(host is not None and not host.closing and window in host.records
                and not host.records[window]['closed'])


def document_owner(widget, owner_type):
    """Locate a retained document rather than its outer application window."""
    while widget is not None:
        if isinstance(widget, owner_type):
            return widget
        widget = widget.parentWidget()
    return None


def close_document(window):
    """Dispatch hosted document close locally, without closing its native ancestor.

    Keep document shutdown separate from native window shutdown after embedding.
    Close handlers still own vetoes, worker retirement and unsaved prompts.
    """
    if window.isWindow():
        return window.close()
    event = qt.QCloseEvent()
    qt.QApplication.sendEvent(window, event)
    if event.isAccepted():
        window.hide()
        if window.testAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose):
            window.deleteLater()
    return event.isAccepted()
