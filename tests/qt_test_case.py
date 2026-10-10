"""Give every Qt test ownership of its windows and background workers."""

from time import monotonic, sleep
import unittest

from commonUtils.ui import pyside as qt
from shiboken6 import isValid


class QtTestCase(unittest.TestCase):
    def run(self, result=None):
        app = qt.QApplication.instance()
        existing = set(app.topLevelWidgets()) if app else set()
        if app:
            palette, stylesheet = app.palette(), app.styleSheet()
            def restore_appearance():
                app.setStyleSheet(stylesheet)
                app.setPalette(palette)
            self.addCleanup(restore_appearance)
        # Run last, after each fixture's own cleanups, before another test starts.
        self.addCleanup(self._release_windows, existing)
        return super().run(result)

    def _release_windows(self, existing):
        app = qt.QApplication.instance()
        if app is None:
            return
        app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        windows = [widget for widget in app.topLevelWidgets() if widget not in existing]
        for window in windows:
            if not isValid(window):
                continue
            for widget in [window, *window.findChildren(qt.QWidget)]:
                if not isValid(widget):
                    continue
                prepare = getattr(widget, 'prepare_close', None)
                if callable(prepare):
                    prepare()
                # FileBrowser.stop cooperatively stops all of its worker owners.
                if type(widget).__name__ == 'FileBrowser':
                    widget.stop()
            window.close()
        deadline = monotonic() + 5
        while True:
            app.processEvents()
            app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            active = [worker for window in windows if isValid(window)
                      for worker in window.findChildren(qt.QThread)
                      if isValid(worker) and worker.isRunning()]
            if not active:
                break
            self.assertLess(monotonic(), deadline, f'Workers did not stop: {active}')
            sleep(.005)
        for window in windows:
            if isValid(window):
                window.deleteLater()
        app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        app.processEvents()
