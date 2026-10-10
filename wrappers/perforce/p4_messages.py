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

# The application
from ...debugUtils import *
from .p4_utils import get_p4_macos_path, get_p4_linux_path

# ----------------------------------------------------------------------------------------------------------------------
# USER DEFINED VARIABLES
tool_name = 'Perforce Wrapper'


# ----------------------------------------------------------------------------------------------------------------------
# CODE


class P4LogMessage:
    def __init__(self):
        pass

    def log(self, msg):
        log(Severity.DEBUG, tool_name, msg)

    # DEBUG LOGS (NEVER Popup)
    def info_log_server_accessible(self):
        msg = 'Perforce Server is Accessible!'
        self.log(msg)

    def under_ws_root(self, name):
        msg = f'"{name}" is under workspace root.'
        self.log(msg)

    def in_client_view(self, name):
        msg = f'"{name}" is in client view.'
        self.log(msg)

    def free_from_other_checkouts(self, name):
        msg = f'"{name}" is free from other checkouts.'
        self.log(msg)

    def not_marked_for_delete(self, name):
        msg = f'"{name}" is not marked for delete.'
        self.log(msg)


class P4ErrorMessage:
    def __init__(self, silent: bool = False):
        self.silent: bool = silent

    def log_error(self, msg):
        log(Severity.ERROR, tool_name, msg, popup=not self.silent)

    # ERRORS (Popup IF NOT SILENT)
    def info_default_connection(self):
        msg = (
            f'Perforce configuration failed.\n\n'
            f'What went wrong:\n'
            f'The application could not access the Perforce environment settings. Perforce must have valid Server, User, '
            f'and Workspace values configured for command-line access.\n\n'
            f'What to do:\n'
            f'Open the Perforce (P4V) application and configure the Environment Settings so that Server, User, '
            f'and Workspace are properly defined.\n\n'
            f'Note: In P4V, this can be found under Connection → Environment Settings. Ensure '
            f'"Use current connection for environment settings" is disabled and the fields are manually filled correctly.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def info_perforce_client_error(self, error: str):
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'Perforce reported the following client error:\n'
            f'"{error}"\n\n'
            f'What to do:\n'
            f'Verify your Perforce connection, workspace configuration, and file status. '
            f'Resolve the issue in Perforce (P4V), then try the operation again.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def info_not_recognized(self):
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'Perforce could not be found on this system. The Perforce command-line tools are required for '
            f'The application to communicate with Perforce.\n\n'
            f'What to do:\n'
            f'Ensure Perforce (P4V) is installed and properly configured. Verify that the Perforce command-line '
            f'tools are available and accessible.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def info_win_p4_cmd_missing(self):
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'The Perforce command-line tool could not be executed due to a permission or access error.\n\n'
            f'What to do:\n'
            f'Ensure Perforce is properly installed and that the Perforce executable is accessible. '
            f'Verify that your system permissions allow execution of the Perforce command-line tools.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def info_mac_p4_cmd_missing(self):
        macos_exec_path = get_p4_macos_path()
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'The Perforce parallel executable could not be run due to a permission restriction. '
            f'macOS may block executables that have not been explicitly authorized or marked as executable.\n\n'
            f'What to do:\n'
            f'Locate the Perforce parallel executable at:\n'
            f'{macos_exec_path}\n\n'
            f'Then do one of the following:\n'
            f'- Right-click the file in Finder and select "Open" to authorize it.\n'
            f'- Or open Terminal and run the following command to enable execution:\n'
            f'sudo chmod +x "{macos_exec_path}"\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def info_linux_p4_cmd_missing(self):
        linux_exec_path = get_p4_linux_path()
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'The Perforce parallel executable could not be run due to a permission restriction. '
            f'The executable may not have the required execute permissions.\n\n'
            f'What to do:\n'
            f'Open a Terminal and run the following command to enable execution:\n'
            f'sudo chmod +x "{linux_exec_path}"\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def info_server_cannot_connect(self):
        msg = (
            f'Perforce connection failed.\n\n'
            f'What went wrong:\n'
            f'The application could not connect to the Perforce server. The server may be unavailable, '
            f'or your connection settings may be incorrect.\n\n'
            f'What to do:\n'
            f'Verify your network and VPN connection, and ensure your Perforce Server and Workspace '
            f'settings are correct in P4V.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def login_token_expired(self):
        msg = (
            'Perforce authentication failed.\n\n'
            'What went wrong:\n'
            'The application could not authenticate to the Perforce server. Most likely, the login token is expired.\n\n'
            'What to do:\n'
            'Open P4V and re-enter your password in the login prompt when prompted.\n\n'
            'Perforce operation aborted.'
        )
        self.log_error(msg)

    def not_under_ws_root(self, name, ws_root):
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'The file "{name}" is not located under the current Perforce workspace root "{ws_root}". '
            f'Perforce can only operate on files that exist within the active workspace.\n\n'
            f'What to do:\n'
            f'Move the file into your workspace folder, or update your Perforce workspace settings '
            f'to include its location.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def not_under_ws_root_elaborate(self, client_name: str, client_root: str):
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'One or more files are not located under the current Perforce workspace root. '
            f'Perforce can only operate on files within the active workspace.\n\n'
            f'Workspace name: "{client_name}"\n\n'
            f'Workspace root: "{client_root}"\n\n'
            f'What to do:\n'
            f'Move the affected file(s) into the workspace root, or update your Perforce workspace '
            f'settings if the root location is incorrect.\n\n'
            f'Note: See the log for additional details.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def not_in_client_view(self, name):
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'The file "{name}" is not included in the current Perforce workspace view. '
            f'Perforce can only operate on files that are mapped in the active workspace.\n\n'
            f'What to do:\n'
            f'Ensure the file is located within a folder mapped by your Perforce workspace, or update your '
            f'workspace view settings to include its location.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def not_in_client_view_elaborate(self, client_name: str):
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'One or more files are not included in the current Perforce workspace view. '
            f'The workspace mapping does not include their location on disk, so Perforce cannot operate on them.\n\n'
            f'Workspace name: "{client_name}"\n\n'
            f'What to do:\n'
            f'Update your Perforce workspace view to include the file location, or move the files into a folder '
            f'already mapped by the workspace.\n\n'
            f'Note: See the log for additional details.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def not_free_from_other_checkouts(self, name, checkout_by: str):
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'The file "{name}" is already checked out by {checkout_by}. Perforce prevents multiple users '
            f'from modifying the same file simultaneously.\n\n'
            f'What to do:\n'
            f'Wait until the file is checked in by the other user, or contact them to coordinate access.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def not_free_from_other_checkouts_elaborate(self, checkout_by: str):
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'One or more files are already checked out by {checkout_by}. Perforce prevents multiple users '
            f'from modifying the same file simultaneously.\n\n'
            f'What to do:\n'
            f'Wait until the files are checked in, or contact the users who have them checked out to coordinate access.\n\n'
            f'Note: See the log for additional details.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def marked_for_delete(self, name):
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'The file "{name}" is currently marked for deletion in Perforce. Files marked for deletion '
            f'cannot be checked out or modified.\n\n'
            f'What to do:\n'
            f'Revert the delete operation in Perforce (P4V), or restore the file if it was deleted unintentionally.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def marked_for_delete_elaborate(self):
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'One or more files are currently marked for deletion in Perforce. Files marked for deletion '
            f'cannot be checked out or modified.\n\n'
            f'What to do:\n'
            f'Revert the delete operation in Perforce (P4V), or restore the files if they were deleted unintentionally.\n\n'
            f'Note: See the log for additional details.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)

    def not_latest_and_not_allow_sync(self, name):
        msg = (
            f'Perforce operation failed.\n\n'
            f'What went wrong:\n'
            f'The file "{name}" is not synced to the latest revision in the Perforce depot. '
            f'This operation does not allow automatic synchronization to prevent overwriting '
            f'local changes or performing unsafe updates.\n\n'
            f'What to do:\n'
            f'Sync the file to the latest revision using Perforce (P4V) before attempting this '
            f'operation again.\n\n'
            f'Note: See the log for additional details.\n\n'
            f'Perforce operation aborted.'
        )
        self.log_error(msg)


class P4CriticalMessage:
    def __init__(self):
        pass

    def log_critical(self, msg):
        log(Severity.CRITICAL, tool_name, msg, popup=True)

    # CRITICAL (Popup AND APPLICATION SHUTDOWN)
    def p4_file_client_or_depot_path_required(self, group=False):
        if group:
            error_from = 'P4FileGroup'
        else:
            error_from = 'P4File'
        msg = f'{error_from}: You must specify (at a minimum) either a client_file or depot_file parameter!'
        self.log_critical(msg)
