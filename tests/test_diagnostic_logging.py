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
