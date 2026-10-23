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

# Blue Hole
from ....runtime.diagnostics import *
from ....runtime.platform import *
from .p4_messages import P4LogMessage, P4ErrorMessage
from .p4_utils import exec_p4_arguments, set_p4_env_settings

# ----------------------------------------------------------------------------------------------------------------------
# USER DEFINED VARIABLES
tool_name = 'Perforce Wrapper'
show_verbose = True


# ----------------------------------------------------------------------------------------------------------------------
# CODE


class P4Info:
    """
    Stores the info from the p4 info command in strings.
    """
    def __init__(self):
        # Define dictionary keys
        self.status = None
        self.user_name = ''
        self.client_name = ''
        self.client_host = ''
        self.client_root = ''
        self.client_stream = ''
        self.client_cwd = ''
        self.peer_address = ''
        self.client_address = ''
        self.server_address = ''
        self.server_root = ''
        self.server_date = ''
        self.server_uptime = ''
        self.server_version = ''
        self.server_id = ''
        self.server_services = ''
        self.server_license = ''
        self.server_license_ip = ''
        self.case_handling = ''

        # Set p4 env settings
        if not set_p4_env_settings():
            self.status = False
            return

        # Update keys
        self.update_fields()

    def update_fields(self):
        # A failed refresh must never leave a previous successful status in place.
        self.status = False
        login = exec_p4_arguments(['login', '-s'])
        login_array = login.lines

        if any('password' in line.lower() and 'invalid or unset' in line.lower() for line in login_array):
            self.status = False
            P4ErrorMessage().login_token_expired()
            return
        if not login.success:
            return

        # Get the information from p4 info
        info = exec_p4_arguments(['info'])
        info_array = info.lines
        if not info_array:
            log(Severity.ERROR, tool_name, 'Perforce returned no connection information.')
            return

        # If could not get info, set status to False
        if "Perforce client error" in info_array[0]:
            self.status = False
            P4ErrorMessage().info_perforce_client_error(info_array[0])
            return

        if "is not recognized" in info_array[0]:
            self.status = False
            P4ErrorMessage().info_not_recognized()
            return

        # Create directory from the output of p4 info
        p4_info_dict = {}
        for item in info_array:

            # If client unknown, perforce connection has not been set properly. Warn user!
            if 'Client unknown.' in item:
                self.status = False
                P4ErrorMessage().info_default_connection()
                return

            if 'Permission denied' in item:
                self.status = False
                match get_os():
                    case OS.WIN:
                        P4ErrorMessage().info_win_p4_cmd_missing()
                    case OS.MAC:
                        P4ErrorMessage().info_mac_p4_cmd_missing()
                    case OS.LINUX:
                        P4ErrorMessage().info_linux_p4_cmd_missing()
                return

            key, separator, value = item.partition(': ')
            if separator:
                p4_info_dict[key] = value

        required = ('User name', 'Client name', 'Client host', 'Client root', 'Current directory',
                    'Peer address', 'Client address', 'Server address', 'Server root', 'Server date', 'Server uptime')
        if not info.success or any(key not in p4_info_dict for key in required):
            log(Severity.ERROR, tool_name, 'Cannot read complete Perforce connection information.')
            return

        # Assign the dictionary keys to the values
        self.status = True
        self.user_name = p4_info_dict['User name']
        self.client_name = p4_info_dict['Client name']
        self.client_host = p4_info_dict['Client host']
        self.client_root = p4_info_dict['Client root']
        self.client_cwd = p4_info_dict['Current directory']
        self.peer_address = p4_info_dict['Peer address']
        self.client_address = p4_info_dict['Client address']
        self.server_address = p4_info_dict['Server address']
        self.server_root = p4_info_dict['Server root']
        self.server_date = p4_info_dict['Server date']
        self.server_uptime = p4_info_dict['Server uptime']

    def is_server_accessible(self, silent=False) -> bool:
        # Check if Perforce server is accessible.
        if self.status is not True:
            P4ErrorMessage(silent).info_server_cannot_connect()
            return False
        else:
            P4LogMessage().info_log_server_accessible()
            return True

    def dialog_box_p4_info(self):
        """
        Dialog box displays perforce connection information.
        """
        if not self.status:
            msg = 'Perforce Connection Could not Be Established'
        else:
            msg = (f'User name: "{self.user_name}"\n'
                   f'Client name: "{self.client_name}"\n'
                   f'Client root: "{self.client_root}"\n'
                   f'Server address: "{self.server_address}"\n'
                   f'Server uptime: "{self.server_uptime}"')

        log(Severity.INFO, tool_name, msg, popup=True)
        return True
