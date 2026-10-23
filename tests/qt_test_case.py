"""Give every Qt test ownership of its windows and background workers."""

from time import monotonic, sleep
from tempfile import TemporaryDirectory
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from unittest.mock import patch
import unittest
import os
import sys
import gc
from pathlib import Path

from commonUtils.ui import pyside as qt
from shiboken6 import isValid


def _load_windows_test_fonts(app):
    """Qt's Windows offscreen backend needs explicit outline-font fixtures."""
    if (sys.platform != 'win32' or qt.QApplication.platformName() != 'offscreen'
            or hasattr(app, '_commonutils_test_font_ids')):
        return
    directory = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
    font_ids = []
    for name in ('segoeui.ttf', 'arial.ttf', 'cour.ttf', 'georgia.ttf'):
        path = directory / name
        font_id = qt.QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            raise RuntimeError(f'Cannot load Windows test font: {path}')
        font_ids.append(font_id)
    # Keep these available throughout the isolated test process, like system
    # fonts on the other desktop platforms. No downloads or dependency changes.
    app._commonutils_test_font_ids = font_ids


class _QtTemporaryDirectory(TemporaryDirectory):
    """Retire the scope's Qt resources before removing its filesystem fixture."""
    def __init__(self, case, **kwargs):
        super().__init__(**kwargs)
        self.case = case
        app = qt.QApplication.instance()
        self.existing = set(app.topLevelWidgets()) if app else set()
        self.cleaned = False
        self.futures = set()
        self.future_lock = Lock()
        submit = ThreadPoolExecutor.submit
        def observed_submit(executor, *args, **kwargs):
            future = submit(executor, *args, **kwargs)
            if isinstance(future, Future):
                with self.future_lock:
                    self.futures.add(future)
            return future
        # A pane can be closed and destroyed inside the test body, before its
        # fixture sees owner.future. Retain its jobs independently of Qt owners.
        self.submit_patch = patch.object(ThreadPoolExecutor, 'submit', observed_submit)
        self.submit_patch.start()

    def futures_finished(self):
        with self.future_lock:
            return all(future.done() for future in self.futures)

    def cleanup(self):
        if not self.cleaned:
            try:
                self.case._release_windows(self.existing)
                self.case.wait_until(self.futures_finished,
                                     message='Executor tasks outlived closed fixture panes')
                super().cleanup()
                self.futures.clear()
                self.cleaned = True
            finally:
                self.submit_patch.stop()


class QtTestCase(unittest.TestCase):
    def temporary_directory(self, **kwargs):
        """TemporaryDirectory-compatible scope, also safe for addCleanup fixtures.

        Register fixture-specific cleanup after this call so it runs first
        (for example discard test buffers or close a private database).
        """
        directory = _QtTemporaryDirectory(self, **kwargs)
        self.addCleanup(directory.cleanup)
        return directory

    def wait_until(self, condition, *, timeout=5, message='Qt operation did not finish', drain_deferred=False):
        """Pump Qt until a condition holds; explicitly drain deletion for shutdown."""
        if timeout <= 0:
            raise ValueError('Timeout must be positive')
        deadline = monotonic() + timeout
        app = qt.QApplication.instance()
        while True:
            if app:
                app.processEvents()
                if drain_deferred:
                    app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            if condition():
                return
            self.assertLess(monotonic(), deadline, message() if callable(message) else message)
            sleep(.005)

    def run(self, result=None):
        app = qt.QApplication.instance()
        if app is None:
            app = QtTestCase._test_app = qt.QApplication([])
        _load_windows_test_fonts(app)
        existing = set(app.topLevelWidgets()) if app else set()
        if app:
            palette, stylesheet, font = app.palette(), app.styleSheet(), app.font()
            def restore_appearance():
                app.setStyleSheet(stylesheet)
                app.setPalette(palette)
                app.setFont(font)
            self.addCleanup(restore_appearance)
        # Final safety net for windows outside managed temporary-directory scopes.
        self.addCleanup(self._release_windows, existing)
        return super().run(result)

    def _release_windows(self, existing):
        app = qt.QApplication.instance()
        if app is None:
            return
        windows = [widget for widget in app.topLevelWidgets() if widget not in existing]
        pending, active = [], []
        close_requested = set()
        futures = set()
        def capture_futures(window):
            futures.update(future for owner in [window, *window.findChildren(qt.QObject)]
                           if isinstance((future := getattr(owner, 'future', None)), Future))
        for window in windows:
            if isValid(window):
                capture_futures(window)
        def ready():
            nonlocal active
            pending.clear()
            for window in windows:
                if not isValid(window):
                    continue
                capture_futures(window)
                window_pending = False
                for widget in [window, *window.findChildren(qt.QWidget)]:
                    if not isValid(widget):
                        continue
                    prepare = getattr(widget, 'prepare_close', None)
                    if callable(prepare) and prepare() is False:
                        pending.append(widget)
                        window_pending = True
                    # FileBrowser.stop returns True while its workers are busy.
                    if type(widget).__name__ == 'FileBrowser' and widget.stop():
                        pending.append(widget)
                        window_pending = True
                if not window_pending and isValid(window) and window not in close_requested:
                    # Some owners initiate cancellation only in closeEvent.
                    # Request closing once, then wait for their threads before
                    # destroying the widget and its native handles.
                    close_requested.add(window)
                    capture_futures(window)
                    window.close()
            active = [worker for window in windows if isValid(window)
                      for worker in window.findChildren(qt.QThread)
                      if isValid(worker) and worker.isRunning()]
            return not pending and not active
        self.wait_until(ready, drain_deferred=True, message=lambda: 'Qt shutdown stalled: pending owners '
                        + repr([type(widget).__name__ for widget in pending])
                        + '; running threads ' + repr([worker.objectName() or type(worker).__name__
                                                      for worker in active]))
        # Some QObject owners use an executor rather than QThread. Destruction
        # cancels their work, but an already-running task may still hold native
        # process/file handles until its Future completes.
        for window in windows:
            if isValid(window):
                capture_futures(window)
                window.deleteLater()
        app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        app.processEvents()
        self.wait_until(lambda: all(future.done() for future in futures),
                        message='Executor tasks did not finish after Qt owner destruction')
        # Signal/callback cycles can retain wrappers after their C++ widgets die.
        # Collect them here on the GUI thread, after all owned workers retire,
        # rather than leaving the next worker allocation to run their finalizers.
        gc.collect()
