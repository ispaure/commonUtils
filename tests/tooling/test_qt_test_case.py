"""Fixture lifecycle ordering, cooperative shutdown and bounded Qt waits."""
from pathlib import Path
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import gc
from weakref import finalize

from shiboken6 import isValid
from commonUtils.ui import pyside as qt
from commonUtils.tests.qt_test_case import QtTestCase, _load_windows_test_fonts


class QtFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_retired_widget_cycles_are_collected_on_gui_thread_after_destruction(self):
        case = QtTestCase()
        existing = set(self.app.topLevelWidgets())
        window = qt.QWidget()
        events = []
        enabled = gc.isenabled()
        gc.disable()
        try:
            child = qt.QWidget(window)
            child.loop = child
            finalize(child, lambda: events.append((qt.QThread.currentThread(), isValid(window))))
            del child
            case._release_windows(existing)
            self.assertEqual(events, [(self.app.thread(), False)])
        finally:
            gc.collect()
            if enabled:
                gc.enable()
            if isValid(window):
                window.deleteLater()
                self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def test_directory_scope_destroys_watchers_before_removing_files(self):
        case = QtTestCase()
        unrelated = qt.QWidget()
        try:
            with case.temporary_directory() as directory:
                path = Path(directory) / 'watched.txt'
                path.write_text('fixture')
                window = qt.QWidget()
                watcher = qt.QFileSystemWatcher([str(path)], window)
                window.show()
                destroyed = []
                window.destroyed.connect(lambda: destroyed.append(path.exists()))
            self.assertEqual(destroyed, [True])
            self.assertFalse(isValid(window))
            self.assertFalse(isValid(watcher))
            self.assertFalse(Path(directory).exists())
            self.assertTrue(isValid(unrelated))
            case.doCleanups()  # Context exit and registered cleanup are idempotent.
        finally:
            unrelated.deleteLater()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def test_fixture_callbacks_run_before_windows_and_directory_cleanup(self):
        events = []
        class Probe(QtTestCase):
            def setUp(self):
                self.temp = self.temporary_directory()
                self.window = qt.QWidget()
                self.window.destroyed.connect(lambda: events.append('window'))
                self.addCleanup(lambda: events.append('fixture'))

            def runTest(self):
                self.assertTrue(Path(self.temp.name).exists())
        probe = Probe()
        result = unittest.TestResult()
        probe.run(result)
        self.assertTrue(result.wasSuccessful(), result.errors)
        self.assertEqual(events, ['fixture', 'window'])
        self.assertFalse(Path(probe.temp.name).exists())

    def test_shutdown_waits_for_pending_owner_and_running_thread(self):
        class Window(qt.QWidget):
            def __init__(self):
                super().__init__()
                self.ready = False
                self.started = False
                self.worker = qt.QThread(self)
                self.worker.start()

            def prepare_close(self):
                if not self.started:
                    self.started = True
                    self.worker.quit()
                    qt.QTimer.singleShot(10, self.finish)
                return self.ready and not self.worker.isRunning()

            def finish(self):
                self.ready = True
        case = QtTestCase()
        with case.temporary_directory():
            window = Window()
        self.assertFalse(isValid(window))
        case.doCleanups()

    def test_wait_delivers_timers_and_reports_timeout(self):
        case = QtTestCase()
        ready = []
        qt.QTimer.singleShot(0, lambda: ready.append(True))
        case.wait_until(lambda: ready, message='timer never arrived')
        with self.assertRaisesRegex(AssertionError, 'specific operation stalled'):
            case.wait_until(lambda: False, timeout=.01, message='specific operation stalled')
        with self.assertRaises(ValueError):
            case.wait_until(lambda: True, timeout=0)

    def test_close_event_can_initiate_thread_shutdown(self):
        class Window(qt.QWidget):
            def __init__(self):
                super().__init__()
                self.worker = qt.QThread(self)
                self.worker.start()

            def closeEvent(self, event):
                self.worker.quit()
                event.accept()
        case = QtTestCase()
        with case.temporary_directory():
            window = Window()
        self.assertFalse(isValid(window))
        case.doCleanups()

    def test_failed_body_still_releases_windows_before_directory(self):
        class Probe(QtTestCase):
            def runTest(self):
                with self.temporary_directory() as directory:
                    self.path = Path(directory)
                    self.window = qt.QWidget()
                    self.fail('intentional body failure')
        probe = Probe()
        result = unittest.TestResult()
        probe.run(result)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.errors, [])
        self.assertFalse(isValid(probe.window))
        self.assertFalse(probe.path.exists())

    def test_pending_shutdown_is_a_failure_and_does_not_delete_fixture_early(self):
        class Window(qt.QWidget):
            ready = False

            def prepare_close(self):
                return self.ready
        case = QtTestCase()
        case.wait_until = partial(case.wait_until, timeout=.01)
        temporary = case.temporary_directory()
        window = Window()
        try:
            with self.assertRaisesRegex(AssertionError, 'pending owners.*Window'):
                temporary.cleanup()
            self.assertTrue(Path(temporary.name).exists())
            self.assertTrue(isValid(window))
        finally:
            window.ready = True
            case.doCleanups()
        self.assertFalse(Path(temporary.name).exists())

    def test_executor_task_finishes_after_owner_destruction_before_directory_removal(self):
        case = QtTestCase()
        stopped = Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            with case.temporary_directory() as directory:
                window = qt.QWidget()
                window.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
                owner = qt.QObject(window)
                future = owner.future = executor.submit(stopped.wait, 5)
                owner.destroyed.connect(lambda: stopped.set())
                window.close()  # Fixture callbacks often queue deletion first.
            self.assertTrue(future.done())
            self.assertTrue(future.result())
            self.assertFalse(Path(directory).exists())
        case.doCleanups()

    def test_windows_offscreen_fonts_load_once_and_missing_fonts_report_failure(self):
        app = SimpleNamespace()
        with patch('commonUtils.tests.qt_test_case.sys', SimpleNamespace(platform='win32')), \
                patch.object(qt.QApplication, 'platformName', return_value='offscreen'), \
                patch.object(qt.QFontDatabase, 'addApplicationFont', side_effect=[1, 2, 3, 4]) as load:
            _load_windows_test_fonts(app)
            _load_windows_test_fonts(app)
            self.assertEqual(load.call_count, 4)
            self.assertEqual(app._commonutils_test_font_ids, [1, 2, 3, 4])
            self.assertEqual([Path(call.args[0]).name for call in load.call_args_list],
                             ['segoeui.ttf', 'arial.ttf', 'cour.ttf', 'georgia.ttf'])
        with patch('commonUtils.tests.qt_test_case.sys', SimpleNamespace(platform='win32')), \
                patch.object(qt.QApplication, 'platformName', return_value='offscreen'), \
                patch.object(qt.QFontDatabase, 'addApplicationFont', return_value=-1):
            with self.assertRaisesRegex(RuntimeError, 'Cannot load Windows test font'):
                _load_windows_test_fonts(SimpleNamespace())

    def test_executor_job_is_retained_when_its_owner_was_already_deleted(self):
        case = QtTestCase()
        released = Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            with case.temporary_directory() as directory:
                window = qt.QWidget()
                owner = qt.QObject(window)
                future = owner.future = executor.submit(released.wait, 5)
                owner.deleteLater()
                self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
                self.assertFalse(isValid(owner))
                qt.QTimer.singleShot(20, self.app, released.set)
            self.assertTrue(future.done())
            self.assertTrue(future.result())
            self.assertFalse(Path(directory).exists())
        case.doCleanups()
