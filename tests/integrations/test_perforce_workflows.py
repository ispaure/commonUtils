"""Checkout outcomes and ordering used by Blue Hole; no server or UI required."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest
from unittest.mock import Mock, patch

from commonUtils.integrations.wrappers import cmdShellWrapper
from commonUtils.integrations.wrappers.perforce import (
    P4File, P4FileGroup, P4FileStatus, PerforceRuntime, configure_runtime,
)
from commonUtils.integrations.wrappers.perforce import p4_file, p4_file_group, p4_info, p4_utils

Result = cmdShellWrapper.CommandResult


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        # Connection/root checks are tested separately; these fixtures isolate the
        # mutation sequence and its final readiness contract.
        for module in (p4_file, p4_file_group):
            self.enterContext(patch.object(module, 'P4Info', return_value=Mock(client_root='/work')))
            self.enterContext(patch.object(module, 'log'))
        self.enterContext(patch.object(P4File, 'is_client_file_under_workspace_root', return_value=True))
        self.enterContext(patch.object(P4File, 'is_in_client_view', return_value=True))
        self.enterContext(patch.object(P4File, 'is_free_from_other_checkouts', return_value=True))
        self.enterContext(patch.object(P4File, 'is_not_marked_for_delete', return_value=True))

    def file_with_refreshes(self, before, after):
        item = P4File('/work/my scene.blend')
        def refresh():
            item.status = states.pop(0)
            return True
        states = [before, after]
        item.update_fields = Mock(side_effect=refresh)
        return item

    def test_existing_edit_and_add_need_no_commands(self):
        for status in (P4FileStatus.CHECKOUT_BY_ME, P4FileStatus.MARKED_FOR_ADD):
            item = self.file_with_refreshes(status, status)
            with patch.object(p4_file, 'exec_p4_arguments') as run:
                self.assertTrue(item.open_for_edit(silent=True))
            run.assert_not_called()

    def test_sync_reload_then_edit_order(self):
        item = self.file_with_refreshes(P4FileStatus.NOT_LATEST_REVISION, P4FileStatus.CHECKOUT_BY_ME)
        events = []
        item._callback_pre_sync = lambda: events.append('before sync')
        item._callback_post_sync = lambda: events.append('reload')
        item._callback_pre_edit = lambda: events.append('before edit')
        item._callback_post_edit = lambda: events.append('after edit')
        def run(arguments):
            events.append(tuple(arguments))
            return Result(0)
        with patch.object(p4_file, 'exec_p4_arguments', side_effect=run):
            self.assertTrue(item.open_for_edit(silent=True))
        self.assertEqual(events, ['before sync', ('sync', '-f', item.clientFile), 'reload',
                                 'before edit', ('edit', item.clientFile), 'after edit'])

    def test_save_disallows_sync_and_declined_checkout_does_nothing(self):
        item = self.file_with_refreshes(P4FileStatus.NOT_LATEST_REVISION, P4FileStatus.CHECKOUT_BY_ME)
        with patch.object(p4_file, 'exec_p4_arguments') as run, patch.object(p4_file, 'P4ErrorMessage'):
            self.assertFalse(item.open_for_edit(silent=True, allow_sync=False))
        run.assert_not_called()
        item = self.file_with_refreshes(P4FileStatus.LATEST_REVISION, P4FileStatus.CHECKOUT_BY_ME)
        with patch.object(p4_file.ui, 'display_msg_box_ok_cancel', return_value=False), patch.object(
                p4_file, 'exec_p4_arguments') as run:
            self.assertFalse(item.open_for_edit())
        run.assert_not_called()

    def test_failed_sync_never_reloads_or_edits(self):
        item = self.file_with_refreshes(P4FileStatus.NOT_LATEST_REVISION, P4FileStatus.CHECKOUT_BY_ME)
        item._callback_post_sync = Mock()
        with patch.object(p4_file, 'exec_p4_arguments', return_value=Result(1, stderr=('sync failed',))) as run:
            self.assertFalse(item.open_for_edit(silent=True))
        item._callback_post_sync.assert_not_called()
        self.assertEqual(run.call_count, 1)

    def test_post_sync_hook_can_change_the_following_checkout_decision(self):
        for silent in (False, True):
            with self.subTest(silent=silent):
                item = self.file_with_refreshes(P4FileStatus.NOT_LATEST_REVISION, P4FileStatus.CHECKOUT_BY_ME)
                item._callback_post_sync = Mock(side_effect=lambda: setattr(item, 'status', P4FileStatus.CHECKOUT_BY_ME))
                with patch.object(p4_file, 'exec_p4_arguments', return_value=Result(0)) as run, \
                        patch.object(p4_file.ui, 'display_msg_box_ok_cancel', return_value=True) as prompt:
                    self.assertTrue(item.open_for_edit(silent=silent))
                run.assert_called_once_with(['sync', '-f', item.clientFile])
                item._callback_post_sync.assert_called_once_with()
                self.assertEqual(prompt.call_count, 0 if silent else 1)

    def test_declining_add_or_sync_stops_before_commands_and_final_refresh(self):
        for status in (P4FileStatus.NOT_ADDED, P4FileStatus.NOT_LATEST_REVISION):
            with self.subTest(status=status):
                item = self.file_with_refreshes(status, P4FileStatus.CHECKOUT_BY_ME)
                with patch.object(p4_file.ui, 'display_msg_box_ok_cancel', return_value=False), \
                        patch.object(p4_file, 'exec_p4_arguments') as run:
                    self.assertFalse(item.open_for_edit())
                run.assert_not_called()
                item.update_fields.assert_called_once_with()

    def test_add_placeholder_preserves_content_and_hooks(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'new export.fbx'
            path.write_bytes(b'export content')
            item = self.file_with_refreshes(P4FileStatus.NOT_ADDED, P4FileStatus.MARKED_FOR_ADD)
            item.clientFile = str(path)
            item._callback_pre_add, item._callback_post_add = Mock(), Mock()
            with patch.object(p4_file, 'exec_p4_arguments', return_value=Result(0)) as run:
                self.assertTrue(item.open_for_edit(silent=True))
            self.assertEqual(path.read_bytes(), b'export content')
            item._callback_pre_add.assert_called_once_with()
            item._callback_post_add.assert_called_once_with()
            run.assert_called_once_with(['add', str(path)])

    def test_move_reports_failure_and_preserves_both_path_arguments(self):
        item = P4File('/work/old name.fbx')
        with patch.object(p4_file, 'exec_p4_arguments', return_value=Result(1)) as run:
            self.assertFalse(item.run_p4_move('/work/new name.fbx'))
        run.assert_called_once_with(['move', item.clientFile, '/work/new name.fbx'])

    def group_with_refreshes(self, before, after):
        group = P4FileGroup()
        for index in range(len(before)):
            group.append_p4_file_to_group_from_client_file(f'/work/export {index}.fbx')
        states = [before, after]
        def refresh():
            for item, status in zip(group.get_p4_file_lst(), states.pop(0)):
                item.status = status
            return True
        group.update_fields_client_n_depot = Mock(side_effect=refresh)
        return group

    def test_batch_checks_every_final_status(self):
        group = self.group_with_refreshes([P4FileStatus.LATEST_REVISION] * 2,
                                         [P4FileStatus.CHECKOUT_BY_ME, P4FileStatus.LATEST_REVISION])
        with patch.object(p4_file_group, 'exec_p4_arguments', return_value=Result(0)):
            self.assertFalse(group.open_for_edit())
        self.assertIn('/work/export 1.fbx', str(p4_file_group.log.call_args_list))

    def test_batch_stops_after_failed_sync(self):
        group = self.group_with_refreshes([P4FileStatus.NOT_LATEST_REVISION], [P4FileStatus.CHECKOUT_BY_ME])
        with patch.object(p4_file_group, 'exec_p4_arguments', return_value=Result(1, stderr=('failed',))) as run:
            self.assertFalse(group.open_for_edit())
        run.assert_called_once_with(['sync', '-f', '/work/export 0.fbx'])

    def test_batch_keeps_add_sync_edit_order_without_individual_hooks(self):
        group = self.group_with_refreshes(
            [P4FileStatus.NOT_ADDED, P4FileStatus.NOT_LATEST_REVISION, P4FileStatus.LATEST_REVISION],
            [P4FileStatus.MARKED_FOR_ADD, P4FileStatus.CHECKOUT_BY_ME, P4FileStatus.CHECKOUT_BY_ME])
        with TemporaryDirectory() as directory:
            for index, item in enumerate(group.get_p4_file_lst()):
                item.clientFile = str(Path(directory) / f'export {index}.fbx')
                item._callback_post_add = Mock(side_effect=AssertionError('batch invoked file hook'))
            with patch.object(p4_file_group, 'exec_p4_arguments', return_value=Result(0)) as run:
                self.assertTrue(group.open_for_edit())
            self.assertEqual([call.args[0][0] for call in run.call_args_list], ['add', 'sync', 'edit'])
            self.assertEqual(Path(group.get_p4_file_lst()[0].clientFile).read_bytes(), b'\0')


class CommandTests(unittest.TestCase):
    def tearDown(self):
        configure_runtime()

    def test_arguments_preserve_spaces_and_shell_characters_on_all_desktop_platforms(self):
        path = '/work/art & props/hero $(touch nope).fbx'
        for platform in (p4_utils.OS.WIN, p4_utils.OS.MAC, p4_utils.OS.LINUX):
            configure_runtime(PerforceRuntime(executable=lambda platform: '/tools/my p4'))
            with patch.object(p4_utils, 'get_os', return_value=platform), patch.object(
                    p4_utils.os.path, 'isfile', return_value=True), patch.object(p4_utils.os, 'stat') as stat, patch.object(
                    p4_utils.os, 'chmod'), patch.object(cmdShellWrapper, 'run_command', return_value=Result(0)) as run:
                stat.return_value.st_mode = 0o755
                result = p4_utils.exec_p4_arguments(['move', path, path + '.new'])
            self.assertTrue(result.success)
            self.assertEqual(run.call_args.args[0], ['/tools/my p4', 'move', path, path + '.new'])
            self.assertFalse(run.call_args.kwargs.get('shell', False))
            self.assertEqual(run.call_args.kwargs['idle_timeout'], 15)

    def test_command_failures_report_diagnostics_and_return_outcomes(self):
        for result in (Result(1, stderr=('permission denied',)), Result(-1, stdout=('partial',), timed_out=True),
                       Result(None, cancelled=True)):
            with patch.object(p4_utils, 'get_os', return_value=p4_utils.OS.WIN), patch.object(
                    cmdShellWrapper, 'run_command', return_value=result), patch.object(p4_utils, 'log') as log:
                self.assertIs(p4_utils.exec_p4_arguments(['edit', 'scene.blend']), result)
            self.assertTrue(log.called)
            self.assertIn('edit', str(log.call_args))

    def test_real_subprocess_receives_literal_arguments(self):
        # Use the interpreter as a fake CLI to exercise actual subprocess
        # transport, rather than only inspecting a mocked call.
        configure_runtime(PerforceRuntime(executable=lambda platform: sys.executable))
        paths = ['art & props/hero.fbx', 'scene $(echo unexpected).blend', r'C:\work\my scene.blend']
        result = p4_utils.exec_p4_arguments(['-c', 'import json,sys; print(json.dumps(sys.argv[1:]))', *paths])
        self.assertTrue(result.success, result.lines)
        self.assertEqual(json.loads(result.lines[0]), paths)

    def test_launch_error_becomes_a_reported_failure(self):
        with patch.object(p4_utils, 'get_os', return_value=p4_utils.OS.WIN), patch.object(
                cmdShellWrapper, 'run_command', side_effect=FileNotFoundError('missing p4')), patch.object(p4_utils, 'log'):
            result = p4_utils.exec_p4_arguments(['edit', 'scene.blend'])
        self.assertFalse(result.success)
        self.assertIn('missing p4', result.stderr[0])

    def test_fstat_accepts_expected_nonzero_missing_file_only(self):
        path = '/work/new export.fbx'
        with patch.object(p4_utils, 'exec_p4_arguments', return_value=Result(1, stderr=(path + ' - no such file(s).',))):
            self.assertEqual(p4_utils.p4_fstat_dict([path]), [{'clientFile': path}])
        for result in (Result(1, stderr=('permission denied',)), Result(0),
                       Result(-1, stdout=('... clientFile ' + path,), timed_out=True)):
            with patch.object(p4_utils, 'exec_p4_arguments', return_value=result), patch.object(p4_utils, 'log'):
                self.assertIsNone(p4_utils.p4_fstat_dict([path]))

    def test_mixed_existing_and_new_export_records_preserve_last_stdout_record(self):
        outcome = Result(1, stdout=('... clientFile /work/existing.fbx', '... isMapped'),
                         stderr=('/work/new.fbx - no such file(s).',))
        with patch.object(p4_utils, 'exec_p4_arguments', return_value=outcome):
            self.assertEqual(p4_utils.p4_fstat_dict(['/work/existing.fbx', '/work/new.fbx']),
                [{'clientFile': '/work/existing.fbx', 'isMapped': ''}, {'clientFile': '/work/new.fbx'}])

    def test_malformed_file_refresh_preserves_identity_and_reports_failure(self):
        item = P4File('/work/scene.blend')
        for records in ([], [{'unexpected': 'diagnostic'}]):
            with patch.object(p4_file, 'p4_fstat_dict', return_value=records), patch.object(p4_file, 'log'):
                self.assertFalse(item.update_fields())
            self.assertEqual(item.clientFile, '/work/scene.blend')

    def test_info_empty_or_malformed_output_does_not_raise_or_retain_success(self):
        with patch.object(p4_info, 'set_p4_env_settings', return_value=True), patch.object(
                p4_info, 'exec_p4_arguments', return_value=Result(0)), patch.object(p4_info, 'log'):
            info = p4_info.P4Info()
            self.assertFalse(info.status)
            info.status = True
            info.update_fields()
            self.assertFalse(info.status)

    def test_info_preserves_colons_in_values_and_failed_refresh_clears_status(self):
        labels = ('User name', 'Client name', 'Client host', 'Client root', 'Current directory',
                  'Peer address', 'Client address', 'Server address', 'Server root', 'Server date', 'Server uptime')
        lines = tuple(f'{key}: value: with colon' for key in labels)
        with patch.object(p4_info, 'set_p4_env_settings', return_value=True), patch.object(
                p4_info, 'exec_p4_arguments', side_effect=[Result(0), Result(0, stdout=lines)]):
            info = p4_info.P4Info()
        self.assertTrue(info.status)
        self.assertEqual(info.client_root, 'value: with colon')
        with patch.object(p4_info, 'exec_p4_arguments', return_value=Result(1)), patch.object(p4_info, 'log'):
            info.update_fields()
        self.assertFalse(info.status)

    def test_group_refresh_rejects_missing_records(self):
        group = P4FileGroup()
        group.append_p4_file_to_group_from_client_file('/work/a.fbx')
        group.append_p4_file_to_group_from_client_file('/work/b.fbx')
        with patch.object(p4_file_group, 'p4_fstat_dict', return_value=[{'clientFile': '/work/a.fbx'}]), patch.object(
                p4_file_group, 'log'):
            self.assertFalse(group.update_fields_client_n_depot())


if __name__ == '__main__':
    unittest.main()
