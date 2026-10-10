# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - SHARED PERFORCE WRAPPER, EXTRACTED FROM BLUE HOLE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

# System
from typing import List, Optional, Union
from pathlib import Path

# Blender

# Blue Hole
from ...debugUtils import log, Severity
from ... import ui, fileUtils
from ...osUtils import OS, get_os
from .p4_messages import P4LogMessage, P4ErrorMessage, P4CriticalMessage
from .p4_file_status import P4FileStatus
from .p4_info import P4Info
from .p4_utils import p4_fstat_dict, create_empty_binary_file, exec_p4_command

# ----------------------------------------------------------------------------------------------------------------------
# USER DEFINED VARIABLES
tool_name = 'Perforce Wrapper'
show_verbose = True


# ----------------------------------------------------------------------------------------------------------------------
# CODE


class P4File:
    def __init__(self, client_file: Optional[str] = None, depot_file: Optional[str] = None):
        # Set fields (if they were given, else is None
        self.depotFile: Optional[str] = depot_file
        self.clientFile: Optional[str] = client_file
        # If both are none, this is a critical error and script should be prevented from progressing further!
        if self.depotFile is None and self.clientFile is None:
            P4CriticalMessage().p4_file_client_or_depot_path_required(group=False)

        # Set fields to their defaults
        self.status: Optional[P4FileStatus] = None
        self.file_name: Optional[str] = None
        self.isMapped: bool = False
        self.notInClientView: bool = False
        self.headAction: Optional[str] = None
        self.headType = None
        self.headTime = None
        self.headRev = None
        self.headChange = None
        self.headModTime = None
        self.haveRev = None
        self.otherOpen0 = None
        self.otherAction0 = None
        self.otherChange0 = None
        self.otherOpen = None
        self.action = None
        self.change = None
        self.type = None
        self.actionOwner = None
        self.workRev = None

    def update_fields(self, f_stat_dict=None) -> bool:
        # If no dict is given for the refresh, fetch info.
        if f_stat_dict is None:
            f_stat_dict = p4_fstat_dict(self.clientFile)
            if f_stat_dict is not None:
                f_stat_dict = f_stat_dict[0]  # There was no error, get the first (only) item to process.
            else:
                return False  # There was an error, return False as could not process properly.

        self.depotFile = self.key_else_default(f_stat_dict, 'depotFile')
        self.clientFile = self.key_else_default(f_stat_dict, 'clientFile')
        self.headAction = self.key_else_default(f_stat_dict, 'headAction')
        self.headType = self.key_else_default(f_stat_dict, 'headType')
        self.headTime = self.key_else_default(f_stat_dict, 'headTime')
        self.headRev = self.key_else_default(f_stat_dict, 'headRev')
        self.headChange = self.key_else_default(f_stat_dict, 'headChange')
        self.headModTime = self.key_else_default(f_stat_dict, 'headModTime')
        self.haveRev = self.key_else_default(f_stat_dict, 'haveRev')
        self.otherOpen0 = self.key_else_default(f_stat_dict, 'otherOpen0')
        self.otherAction0 = self.key_else_default(f_stat_dict, 'otherAction0')
        self.otherChange0 = self.key_else_default(f_stat_dict, 'otherChange0')
        self.otherOpen = self.key_else_default(f_stat_dict, 'otherOpen')
        self.action = self.key_else_default(f_stat_dict, 'action')
        self.change = self.key_else_default(f_stat_dict, 'change')
        self.type = self.key_else_default(f_stat_dict, 'type')
        self.actionOwner = self.key_else_default(f_stat_dict, 'actionOwner')
        self.workRev = self.key_else_default(f_stat_dict, 'workRev')

        self.file_name = self.clientFile.split('\\')[-1]

        # Give label on if it's mapped or not
        if 'isMapped' in f_stat_dict.keys():
            self.isMapped = True
        else:
            self.isMapped = False

        # Give label on if it's in client view or not
        if 'notInClientView' in f_stat_dict.keys():
            self.notInClientView = True
        else:
            self.notInClientView = False

        # Deduce the simple current status of the file
        self.status = self.get_status()

        # Completed successfully
        return True

    def get_display_name(self):
        # Prefer clientFile as a display name, else use depotFile as fallback. One of the two is guaranteed available.
        if self.clientFile is not None:
            return self.clientFile
        else:
            return self.depotFile

    def key_else_default(self, dictionary: dict, key: str, default_value=None):
        """
        Returns the value of a key from a dict. If key was not found, return default value instead (default is None).
        Prevents unavailable key from being an error.
        :param dictionary: Dictionary to look into for key
        :param key: Key to look for in dictionary
        :param default_value: Value to put if key was not found (can be any type)
        :rtype: Can be any type
        """
        if key in dictionary.keys():
            return dictionary[key]
        else:
            return default_value

    def get_status(self):
        """
        Deduce the simple current status of the file
        :rtype: P4FileStatus
        """
        if self.headAction == 'delete' and self.action == 'add':
            return P4FileStatus.MARKED_FOR_ADD
        if not self.isMapped or self.headAction == 'move/delete' or self.headAction == 'delete':
            return P4FileStatus.NOT_ADDED
        elif self.headAction == 'add' and self.action == 'delete':
            return P4FileStatus.MARKED_FOR_DELETE
        elif self.action == 'add':
            return P4FileStatus.MARKED_FOR_ADD
        elif self.action == 'edit':
            return P4FileStatus.CHECKOUT_BY_ME
        elif self.otherOpen is not None:
            return P4FileStatus.CHECKOUT_BY_OTHER
        elif self.haveRev == self.headRev:
            return P4FileStatus.LATEST_REVISION
        elif self.haveRev != self.headRev:
            return P4FileStatus.NOT_LATEST_REVISION
        else:
            return P4FileStatus.INVALID

    def log_info(self):
        """
        Print some information about the file, for debug purposes
        """
        info = (f'File Name: {self.file_name}\n'
                f'Status: {self.status}\n'
                f'Depot File: {self.depotFile}\n'
                f'Client File: {self.clientFile}\n'
                f'Is Mapped: {self.isMapped}\n'
                f'Not in Client View: {self.notInClientView}\n'
                f'Head Action: {self.headAction}\n'
                f'Head Type: {self.headType}\n'
                f'Head Time: {self.headTime}\n'
                f'Head Revision: {self.headRev}\n'
                f'Head Change: {self.headChange}\n'
                f'Head Modification Time: {self.headModTime}\n'
                f'Have Revision: {self.haveRev}\n'
                f'Other Open 0: {self.otherOpen0}\n'
                f'Other Action 0: {self.otherAction0}\n'
                f'Other Change 0: {self.otherChange0}\n'
                f'Other Open: {self.otherOpen}\n'
                f'Action: {self.action}\n'
                f'Change: {self.change}\n'
                f'Type: {self.type}\n'
                f'Action Owner: {self.actionOwner}\n'
                f'Work Revision: {self.workRev}\n')
        log(Severity.INFO, tool_name, info, popup=True)

    def is_client_file_under_workspace_root(self, p4_info_cls: P4Info, silent: bool = False):
        if self.clientFile is not None:
            normalized_client_root = str(
                Path(p4_info_cls.client_root))  # Sometime it outputs with / or not, so normalize here.

            # If on Windows, should test in lowercase (not be case-sensitive)
            match get_os():
                case OS.WIN:
                    client_file_str = self.clientFile.lower()
                    client_root_str = normalized_client_root.lower()
                case OS.MAC | OS.LINUX:
                    client_file_str = self.clientFile
                    client_root_str = normalized_client_root

            if client_file_str.startswith(f'{client_root_str}{fileUtils.get_split_character()}'):
                P4LogMessage().under_ws_root(self.get_display_name())
                return True
        P4ErrorMessage(silent).not_under_ws_root(self.get_display_name(), p4_info_cls.client_root)
        return False

    def is_in_client_view(self, silent: bool = False):
        if self.notInClientView:
            P4ErrorMessage(silent).not_in_client_view(self.get_display_name())
            return False
        else:
            P4LogMessage().in_client_view(self.get_display_name())
            return True

    def is_free_from_other_checkouts(self, silent: bool = False):
        if self.status is P4FileStatus.CHECKOUT_BY_OTHER:
            P4ErrorMessage(silent).not_free_from_other_checkouts(self.get_display_name(), self.otherOpen0)
            return False
        else:
            P4LogMessage().free_from_other_checkouts(self.get_display_name())
            return True

    def is_not_marked_for_delete(self, silent: bool = False):
        if self.status is P4FileStatus.MARKED_FOR_DELETE:
            P4ErrorMessage(silent).marked_for_delete(self.get_display_name())
            return False
        else:
            P4LogMessage().not_marked_for_delete(self.get_display_name())
            return True

    def __run_p4_cmd(self, command: str,
                     incl_status_lst: Union[List[P4FileStatus], None] = None,
                     excl_status_lst: Union[List[P4FileStatus], None] = None,
                     move_to: Optional[str] = None):

        # See if command can be run, return if cannot
        if incl_status_lst is not None:
            if not self.status in incl_status_lst:
                return False
        if excl_status_lst is not None:
            if self.status in excl_status_lst:
                return False

        # If add command, create file before checkout if doesn't exist (may be created later)
        if 'p4 add' in command and self.clientFile is not None:
            create_empty_binary_file(self.clientFile)

        # Run command for p4_file
        display_name = self.get_display_name()
        if move_to is None:
            exec_p4_command(f'{command} {display_name}')
        else:
            exec_p4_command(f'{command} {display_name} {move_to}')

    def _run_p4_add(self):
        self._callback_pre_add()
        self.__run_p4_cmd(command='p4 add', incl_status_lst=[P4FileStatus.NOT_ADDED])
        self._callback_post_add()

    def _run_p4_sync(self):
        self._callback_pre_sync()
        # progress_bar = ui.pyside.display_progress_bar(f'{tool_name}: Getting Latest...')
        # progress_bar.update_progress(10)
        self.__run_p4_cmd(command='p4 sync -f', incl_status_lst=[P4FileStatus.NOT_LATEST_REVISION])
        # progress_bar.update_progress(100)
        # progress_bar.dlg.close()
        self._callback_post_sync()

    def _run_p4_edit(self):
        self._callback_pre_edit()
        self.__run_p4_cmd(command='p4 edit', excl_status_lst=[P4FileStatus.NOT_ADDED, P4FileStatus.MARKED_FOR_ADD,
                                                              P4FileStatus.CHECKOUT_BY_ME])
        self._callback_post_edit()

    def _callback_pre_add(self):
        pass

    def _callback_post_add(self):
        pass

    def _callback_pre_sync(self):
        pass

    def _callback_post_sync(self):
        pass

    def _callback_pre_edit(self):
        pass

    def _callback_post_edit(self):
        pass

    def open_for_edit(self, silent: bool = False, allow_sync: bool = True):

        msg = (
            'P4File.open_for_edit: Running single-file open_for_edit, which is costly to run in a loop. Please only use '
            'for explicit checkout requiring user interaction. For batch checkout, use P4FileGroup.open_for_edit instead '
            'as it is more optimized!')
        log(Severity.WARNING, tool_name, msg)

        # Perforce Server accessible Check
        p4_info_cls = P4Info()
        if not p4_info_cls.is_server_accessible(silent):
            return False
        elif not self.is_client_file_under_workspace_root(p4_info_cls, silent=True):
            P4ErrorMessage(silent).not_under_ws_root_elaborate(p4_info_cls.client_name, p4_info_cls.client_root)
            return False

        # Update fields
        result = self.update_fields()
        if not result:  # Fields didn't properly get set
            return False

        # Perform other checks before checkout
        elif not self.is_in_client_view(silent=True):
            P4ErrorMessage(silent).not_in_client_view_elaborate(p4_info_cls.client_name)
            return False
        elif not self.is_free_from_other_checkouts(silent=True):
            P4ErrorMessage(silent).not_free_from_other_checkouts_elaborate(self.otherOpen0)
            return False
        elif not self.is_not_marked_for_delete(silent=True):
            P4ErrorMessage(silent).marked_for_delete_elaborate()
            return False

        # Mark not added for add
        if self.status in [P4FileStatus.NOT_ADDED]:
            if silent:
                self._run_p4_add()
            else:
                msg = f'File "{self.file_name}" is not marked for add. Do you want to mark for add?'
                msg_box_result = ui.display_msg_box_ok_cancel(tool_name, msg)
                if msg_box_result:
                    self._run_p4_add()
                else:
                    return False

        # Get latest on files that are not at latest
        if self.status in [P4FileStatus.NOT_LATEST_REVISION]:
            if not allow_sync:
                P4ErrorMessage(silent).not_latest_and_not_allow_sync(self.get_display_name())
                return False
            if silent:
                self._run_p4_sync()
            else:
                msg = f'File "{self.file_name}" is not synced to the latest revision. Sync to the latest revision?'
                msg_box_result = ui.display_msg_box_ok_cancel(tool_name, msg)
                if msg_box_result:
                    self._run_p4_sync()
                else:
                    return False

        # Checkout files that re not checked out yet
        if self.status not in [P4FileStatus.NOT_ADDED, P4FileStatus.MARKED_FOR_ADD, P4FileStatus.CHECKOUT_BY_ME]:
            if silent:
                self._run_p4_edit()
            else:
                msg = f'File "{self.file_name}" is not checked out. Check out?'
                msg_box_result = ui.display_msg_box_ok_cancel(tool_name, msg)
                if msg_box_result:
                    self._run_p4_edit()
                else:
                    return False

        # Update fields
        result = self.update_fields()
        if not result:  # Fields didn't properly get set
            return False

        # If not checked out or marked for add, did not succeed
        if self.status not in [P4FileStatus.MARKED_FOR_ADD, P4FileStatus.CHECKOUT_BY_ME]:
            msg = f'File "{self.file_name}" could not be successfully checked out! Check log for details.'
            log(Severity.ERROR, tool_name, msg)
            return False

        return True

    def run_p4_move(self, move_to_path_str):
        self.__run_p4_cmd(command='p4 move', move_to=move_to_path_str)
