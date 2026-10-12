"""One application-owned polling timer; subscriber callbacks run on the GUI thread."""
import logging
from inspect import ismethod
from pathlib import Path
from weakref import WeakMethod
from .. import pyside as qt
from ...configuration.monitor import settings_monitor


class SettingsSubscription(qt.QObject):
    changed = qt.Signal()

    def __init__(self, paths, callback, owner):
        super().__init__(owner)
        self.paths = (paths,) if isinstance(paths, (str, Path)) else tuple(paths)
        self.callback = WeakMethod(callback) if ismethod(callback) else lambda: callback
        self.unsubscribe = None
        self.changed.connect(self._deliver, qt.Qt.ConnectionType.QueuedConnection)
        self.start()

    def start(self):
        if self.unsubscribe is None:
            self.unsubscribe = settings_monitor().subscribe(self.paths, self._enqueue)
            # A plain callable remains connected during QObject destruction;
            # a slot on this same object is already disconnected at that point.
            self.destroyed.connect(self.unsubscribe)

    def stop(self, *_args):
        if self.unsubscribe is not None:
            try:
                self.destroyed.disconnect(self.unsubscribe)
            except RuntimeError:
                pass  # The owner may already have destroyed this QObject.
            self.unsubscribe()
            self.unsubscribe = None

    def _enqueue(self):
        self.changed.emit()

    def _deliver(self):
        callback = self.callback()
        if self.unsubscribe is not None and callback is not None:
            try:
                callback()
            except Exception:
                logging.exception('Settings view could not refresh')


def subscribe_settings(paths, callback, owner):
    """Retain the subscription with its QObject owner; destruction unsubscribes."""
    app = qt.QApplication.instance()
    if app is None:
        raise RuntimeError('Create QApplication before subscribing to settings')
    if not hasattr(app, '_commonutils_settings_timer'):
        timer = app._commonutils_settings_timer = qt.QTimer(app)
        timer.setInterval(500)
        timer.timeout.connect(settings_monitor().poll)
        timer.start()
    return SettingsSubscription(paths, callback, owner)
