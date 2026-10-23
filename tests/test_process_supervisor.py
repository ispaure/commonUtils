"""Resource ownership remains correct when worker startup or command execution fails."""
from unittest import TestCase
from unittest.mock import Mock, patch
from commonUtils.integrations.wrappers.cmdShellWrapper.process import ProcessSupervisor


class ProcessSupervisorTests(TestCase):
    def test_failed_worker_start_still_stops_child_and_closes_streams(self):
        child = Mock()
        child.poll.return_value = None
        worker = Mock(ident=None)
        worker.start.side_effect = RuntimeError('cannot start thread')
        with patch('threading.Thread', return_value=worker), \
                patch('commonUtils.integrations.wrappers.cmdShellWrapper.process.terminate_process_tree') as stop, \
                patch('commonUtils.integrations.wrappers.cmdShellWrapper.process.close_process_streams') as close:
            with self.assertRaisesRegex(RuntimeError, 'cannot start'):
                with ProcessSupervisor(child) as supervisor:
                    supervisor.start(lambda: None)
            stop.assert_called_once_with(child)
            close.assert_called_once_with(child)
            worker.join.assert_not_called()

    def test_exception_after_parent_exit_still_stops_descendants(self):
        child = Mock()
        child.poll.return_value = 0
        with patch('commonUtils.integrations.wrappers.cmdShellWrapper.process.terminate_process_tree') as stop, \
                patch('commonUtils.integrations.wrappers.cmdShellWrapper.process.close_process_streams'):
            with self.assertRaises(ValueError):
                with ProcessSupervisor(child):
                    raise ValueError('failed consumer')
            stop.assert_called_once_with(child)
