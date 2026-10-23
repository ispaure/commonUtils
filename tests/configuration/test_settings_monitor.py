"""One change detector, weak lifetimes and completed-write notifications."""
import gc
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.configuration.monitor import SettingsMonitor, settings_monitor
from commonUtils.configuration.layered import LayeredSettings


class SettingsMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'preferences.ini'
        self.monitor = SettingsMonitor()

    def test_creation_edit_replacement_and_deletion_notify_matching_subscribers(self):
        calls = []
        self.monitor.subscribe(self.path, lambda: calls.append(True))
        self.path.write_text('one')
        self.monitor.poll()
        self.path.write_text('two changed')
        self.monitor.poll()
        replacement = self.path.with_suffix('.new')
        replacement.write_text('replaced')
        replacement.replace(self.path)
        self.monitor.poll()
        self.path.unlink()
        self.monitor.poll()
        self.monitor.poll()
        self.assertEqual(calls, [True] * 4)

    def test_unsubscribe_is_idempotent_and_removes_watched_paths(self):
        calls = []
        unsubscribe = self.monitor.subscribe(self.path, lambda: calls.append(True))
        unsubscribe(); unsubscribe()
        self.monitor.notify((self.path,))
        self.assertEqual(calls, [])
        self.assertEqual(self.monitor._stamps, {})

    def test_bound_callbacks_do_not_retain_closed_consumers(self):
        class Consumer:
            def changed(self):
                raise AssertionError('Disposed consumer must not be called')
        consumer = Consumer()
        self.monitor.subscribe(self.path, consumer.changed)
        del consumer
        gc.collect()
        self.monitor.notify()
        self.assertEqual(self.monitor._subscriptions, {})
        self.assertEqual(self.monitor._stamps, {})

    def test_failing_consumer_does_not_prevent_other_updates(self):
        calls = []
        def fail():
            raise ValueError('bad view')
        self.monitor.subscribe(self.path, fail)
        self.monitor.subscribe(self.path, lambda: calls.append(True))
        with self.assertLogs(level='ERROR'):
            self.monitor.notify()
        self.assertEqual(calls, [True])

    def test_layered_save_notifies_after_publication_without_duplicate_poll(self):
        defaults = self.path.with_name('defaults.ini')
        defaults.write_text('[Options]\nvalue_str=default\n')
        store = LayeredSettings(defaults, self.path)
        values = []
        unsubscribe = settings_monitor().subscribe((defaults, self.path), lambda: values.append(store.values()))
        self.addCleanup(unsubscribe)
        store.save({('Options', 'value_str'): 'saved'})
        settings_monitor().poll()
        self.assertEqual(values, [{('Options', 'value_str'): 'saved'}])


if __name__ == '__main__':
    unittest.main()
