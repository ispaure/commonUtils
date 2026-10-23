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

from typing import *

# Blue Hole
import os
from ....runtime.diagnostics import *
from .p4_messages import P4ErrorMessage, P4CriticalMessage
from .p4_file_status import P4FileStatus
from .p4_info import P4Info
from .p4_file import P4File
from .p4_utils import p4_fstat_dict, create_empty_binary_file, exec_p4_arguments

# ----------------------------------------------------------------------------------------------------------------------
# USER DEFINED VARIABLES
tool_name = 'Perforce Wrapper'
show_verbose = True


# ----------------------------------------------------------------------------------------------------------------------
# CODE


class P4FileGroup:
    """
    Optimized way of working (batch calls), use this instead of running P4File in a forloop whenever possible.
    """

    def __init__(self):
        self.__p4_file_lst: List[P4File] = []

    def get_p4_file_lst(self) -> List[P4File]:
        return self.__p4_file_lst

    def append_p4_file_to_group_from_client_file(self, client_file):
        p4_file = P4File(client_file=client_file)
        self.__p4_file_lst.append(p4_file)

    def append_p4_file_to_group_from_depot_file(self, depot_file):
        p4_file = P4File(depot_file=depot_file)
        self.__p4_file_lst.append(p4_file)

    def get_p4_file_with_client_file_dict(self) -> Dict[str, P4File]:
        p4_file_dict = {}
        for p4_file in self.__p4_file_lst:
            if p4_file.clientFile is not None:
                p4_file_dict[p4_file.clientFile] = p4_file
        return p4_file_dict

    def get_p4_file_with_depot_file_and_no_client_file(self):
        p4_file_with_client_file_dict = self.get_p4_file_with_client_file_dict()
        p4_file_dict = {}
        for p4_file in self.__p4_file_lst:
            if p4_file not in p4_file_with_client_file_dict.values():
                if p4_file.depotFile is not None:
                    p4_file_dict[p4_file.depotFile] = p4_file
                else:
                    P4CriticalMessage().p4_file_client_or_depot_path_required(group=True)
        return p4_file_dict

    def update_fields_client_n_depot(self):
        """
        Create dictionary of clientFile & depotFile and update fields and match.
        """

        # Update fields for Dict [clientFile (str), P4File]
        client_file_p4_file_dict = self.get_p4_file_with_client_file_dict()
        if not self.update_fields_by_matching_key('clientFile', client_file_p4_file_dict):
            return False

        # Update fields for Dict [depotFile (str), P4File]
        depot_file_p4_file_dict = self.get_p4_file_with_depot_file_and_no_client_file()
        if not self.update_fields_by_matching_key('depotFile', depot_file_p4_file_dict):
            return False

        # Completed
        return True

    def update_fields_by_matching_key(self, fstat_key: str, p4_file_dict: Dict[str, P4File]):
        """
        Batch operation. Updates the fields of a dictionary of P4 Files, where the key is either clientFile or
        depotFile. A fstat_key parameter is given, saying what's the key (clientFile or depotFile)
        """
        if fstat_key not in ['depotFile', 'clientFile']:
            log(Severity.CRITICAL, tool_name, 'Update fields by matching key: fstat_key is invalid')
            return False

        file_path_string_lst = list(_path_batches(p4_file_dict))
        matched = set()
        call_counter = 0
        for file_path_string in file_path_string_lst:
            # Print number of call executed, to give progress feedback...
            call_counter += 1
            log(Severity.DEBUG, tool_name, f'Issuing Call (from {fstat_key}) # {call_counter} of {len(file_path_string_lst)}')

            # Inquire and get results as a lst of dicts
            result_dicts_lst = p4_fstat_dict(file_path_string)
            if not result_dicts_lst:
                return False  # There was an error fetching the dict

            for result_dict in result_dicts_lst:
                result_match_key = result_dict.get(fstat_key)
                if not result_match_key:
                    log(Severity.ERROR, tool_name, f'Incomplete Perforce status: missing {fstat_key}')
                    return False
                match_p4_file: Optional[P4File] = None

                # If on Windows and cannot find key, attempt by ignoring case. Other platform YOLO it that way too.
                if result_match_key not in p4_file_dict.keys():
                    result_match_key_lower = result_match_key.lower()
                    for original_key in p4_file_dict.keys():
                        original_key_lower = original_key.lower()
                        if original_key_lower == result_match_key_lower:
                            match_p4_file = p4_file_dict[original_key]
                            break
                else:
                    match_p4_file = p4_file_dict[result_match_key]

                if match_p4_file is not None:
                    if not match_p4_file.update_fields(result_dict):
                        return False
                    matched.add(id(match_p4_file))
                else:
                    msg = f'Could not match key {fstat_key} {result_match_key} to a P4File!'
                    log(Severity.ERROR, tool_name, msg)
                    return False

        missing = [item.get_display_name() for item in p4_file_dict.values() if id(item) not in matched]
        if missing:
            log(Severity.ERROR, tool_name, f'Perforce returned no status for: {missing}')
            return False
        return True  # Worked properly for all

    def force_get_latest(self):
        return self.__run_p4_cmd_on_p4_file_lst(command=['sync', '-f'])

    def __run_p4_cmd_on_p4_file_lst(self, command,
                                    incl_status_lst=None, excl_status_lst=None):
        # Keep client/depot batches separate; only local add targets need a
        # placeholder. Group operations deliberately do not invoke scene hooks.
        for paths, local in ((self.get_p4_file_with_client_file_dict(), True),
                             (self.get_p4_file_with_depot_file_and_no_client_file(), False)):
            selected = {path: item for path, item in paths.items()
                        if (incl_status_lst is None or item.status in incl_status_lst)
                        and (excl_status_lst is None or item.status not in excl_status_lst)}
            if local and command[0] == 'add':
                for path in selected:
                    create_empty_binary_file(path)
            for batch in _path_batches(selected):
                if not exec_p4_arguments([*command, *batch]).success:
                    return False
        return True

    def open_for_edit(self):
        """
        Accurate method of opening files for edit (Get latest if needed, only checks out if not checked out yet, warning if someone else has the file, etc.)
        """

        # Check Perforce server is accessible
        p4_info_cls = P4Info()
        if not p4_info_cls.is_server_accessible():
            return False
        if not self.is_client_file_under_workspace_root(p4_info_cls):
            return False

        # Update fields
        result = self.update_fields_client_n_depot()
        if not result:  # Fields didn't properly get set
            return False

        # Perform Checks before Proceeding
        if not self.is_in_client_view(p4_info_cls):
            return False
        if not self.is_free_from_other_checkouts():
            return False
        if not self.is_not_marked_for_delete():
            return False

        # Mark not added for add
        if not self.__run_p4_cmd_on_p4_file_lst(command=['add'], incl_status_lst=[P4FileStatus.NOT_ADDED]):
            return False

        # Get latest on files that are not at latest
        if not self.__run_p4_cmd_on_p4_file_lst(command=['sync', '-f'], incl_status_lst=[P4FileStatus.NOT_LATEST_REVISION]):
            return False

        # Checkout files that re not checked out yet
        if not self.__run_p4_cmd_on_p4_file_lst(command=['edit'],
                                         excl_status_lst=[P4FileStatus.NOT_ADDED,
                                                          P4FileStatus.MARKED_FOR_ADD,
                                                          P4FileStatus.CHECKOUT_BY_ME]):
            return False

        # Update fields
        result = self.update_fields_client_n_depot()
        if not result:  # Fields didn't properly get set
            return False

        ready = (P4FileStatus.MARKED_FOR_ADD, P4FileStatus.CHECKOUT_BY_ME)
        failed = [item.get_display_name() for item in self.__p4_file_lst if item.status not in ready]
        if failed:
            log(Severity.ERROR, tool_name, f'Files could not be prepared for editing: {failed}')
            return False
        return True

    def is_client_file_under_workspace_root(self, p4_info_cls: P4Info) -> bool:
        # Validate all clientFile entries for asset are under the current workspace root
        p4_ws_root = p4_info_cls.client_root
        not_under_ws_root = []
        for p4_file in self.__p4_file_lst:
            if not p4_file.is_client_file_under_workspace_root(p4_info_cls, silent=True):
                not_under_ws_root.append(p4_file)
        # If at least one clientFile was not under the workspace root, show error dialogue and exit process
        if len(not_under_ws_root) > 0:
            P4ErrorMessage().not_under_ws_root_elaborate(p4_info_cls.client_name, p4_info_cls.client_root)
            return False
        return True

    def is_in_client_view(self, p4_info_cls: P4Info) -> bool:
        # Check if not in client view
        not_in_client_view = []
        for p4_file in self.__p4_file_lst:
            if not p4_file.is_in_client_view(silent=True):
                not_in_client_view.append(p4_file)
        # If at least one file was not in client view, show error dialogue and exit process
        if len(not_in_client_view) > 0:
            P4ErrorMessage().not_in_client_view_elaborate(p4_info_cls.client_name)
            return False
        return True

    def is_free_from_other_checkouts(self) -> bool:
        p4_checked_out_others_lst = [
            p4_file for p4_file in self.__p4_file_lst
            if not p4_file.is_free_from_other_checkouts()
        ]

        if p4_checked_out_others_lst:
            # Collect all otherOpen0 strings
            other_open_strings = [
                str(p4_file.otherOpen0)
                for p4_file in p4_checked_out_others_lst
                if p4_file.otherOpen0
            ]

            # Remove duplicates while preserving order
            unique_strings = list(dict.fromkeys(other_open_strings))

            # Join into single string
            joined_string = ", ".join(unique_strings)

            P4ErrorMessage().not_free_from_other_checkouts_elaborate(joined_string)

            return False

        return True

    def is_not_marked_for_delete(self):
        # Check if files are marked for delete elsewhere
        p4_marked_delete_lst = []
        for p4_file in self.__p4_file_lst:
            if not p4_file.is_not_marked_for_delete():
                p4_marked_delete_lst.append(p4_file)
        # If at least one file was marked for delete elsewhere, display error message.
        if len(p4_marked_delete_lst) > 0:
            P4ErrorMessage().marked_for_delete_elaborate()
            return False  # Did not run as intended.
        return True

    def append_lst_to_string_max_length(self, lst, split_str, max_str_length, quotation_marks=False):
        """
        Append elements of a list to a string (if the result is less than specific string maximum length). When limit is
        to be reached, append to a second string and so on, so forth.
        :param lst: List of elements to append to the string(s)
        :type lst: lst
        :param split_str: Segment to put in-between appends
        :type split_str: str
        :param max_str_length: Maximum character length allowed for a string
        :type max_str_length: int
        :param quotation_marks: When true, puts quotation marks at start/end of each element in list
        :type quotation_marks: bool
        """
        # Create strings of limited length
        file_str_lst = []
        file_str = ''
        for item in lst:
            if quotation_marks:
                item = '"' + item + '"'
            if len(file_str) + len(item) + len(split_str) > max_str_length:  # If longer than max length
                file_str_lst.append(file_str)  # Append string to list of strings to execute
                file_str = ''  # Reset string
            file_str += item + split_str

        # Add what is left in file_str to file_str_lst
        if file_str != '':
            file_str_lst.append(file_str)

        # Remove the in-between at the end of each string of the array.
        file_str_lst_final = []
        for string in file_str_lst:
            file_str_lst_final.append(string[:-len(split_str)])

        # Return array of strings
        return file_str_lst


def _path_batches(paths, max_length=1000):
    """Conservative command batches without serializing or splitting any path."""
    batch, length = [], 0
    for path in paths:
        cost = len(path) + 3  # Retain the existing conservative batching budget.
        if batch and length + cost > max_length:
            yield batch
            batch, length = [], 0
        batch.append(path)
        length += cost
    if batch:
        yield batch
