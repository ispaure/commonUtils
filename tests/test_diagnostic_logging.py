"""Host logging settings, presentation and failure policies do not leak between instances."""
import unittest
from commonUtils.runtime.diagnostics import DebugLogger, LoggingOptions, DebugException, Severity, noninteractive_logging


class DiagnosticLoggingTests(unittest.TestCase):
    def test_independent_options_sinks_and_explicit_presenters(self):
        events, other, dialogs = [], [], []
        first = DebugLogger(options=LoggingOptions(project_prefix='First', use_time_delta=False), sinks=[events.append], presenter=lambda *args: dialogs.append(args))
        second = DebugLogger(sinks=[other.append])
        first.log_debug(Severity.WARNING, 'Title', 'Message', popup=True)
        self.assertEqual(events[0].text, '[WRN] First | Title: Message')
        self.assertEqual(dialogs, [('First | Title', 'Message')])
        self.assertEqual(other, [])
        self.assertIsNone(second.options.project_prefix)
        with noninteractive_logging():
            with self.assertRaises(DebugException):
                first.log_debug(Severity.CRITICAL, 'Worker', 'Failure')
        self.assertEqual(len(dialogs), 1)
        first.configure(verbose_debug=False)
        first.log_debug(Severity.DEBUG, 'Hidden', 'Hidden')
        self.assertEqual(len(events), 2)

    def test_presentation_is_optional_and_failure_policy_is_explicit(self):
        events = []
        logger = DebugLogger(sinks=[events.append], raise_critical=False)
        logger.log_debug(Severity.CRITICAL, 'Failure', 'Diagnostic only')
        self.assertEqual(len(events), 1)
        self.assertIsNone(logger.presenter)

    def test_multiline_color_and_file_output_keep_the_existing_format(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        events = []
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'events.log'
            logger = DebugLogger(path, options=LoggingOptions(use_time_delta=False, write_to_log=True), sinks=[events.append])
            logger.log_debug(Severity.ERROR, 'Title', 'one\ntwo')
            expected = '[ERR] Title\n      one\n      two\n'
            self.assertEqual(events[0].text, expected)
            self.assertEqual(events[0].colored, '\033[31m' + expected + '\033[0m')
            self.assertEqual(path.read_text(), expected + '\n')

    def test_instances_copy_supplied_options(self):
        options = LoggingOptions(project_prefix='Original')
        first, second = DebugLogger(options=options), DebugLogger(options=options)
        options.project_prefix = 'External edit'
        first.configure(project_prefix='First')
        self.assertEqual(first.options.project_prefix, 'First')
        self.assertEqual(second.options.project_prefix, 'Original')
