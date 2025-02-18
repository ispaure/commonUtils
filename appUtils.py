from typing import *
from pathlib import Path
import os
import subprocess

# Common utilities
from commonUtils import fileUtils
from commonUtils.osUtils import *
from commonUtils.pySideUtils import *

# Wrappers
from commonUtils.wrappers import cmdShellWrapper, powerShellWrapper


class App:
    def __init__(self, name):
        self.name = name


class DiskApp(App):
    def __init__(self, name, exec_path: Union[str, Path, None], install_path: Union[Path, None] = None):
        super().__init__(name)
        self.exec_path = exec_path
        self.install_path = install_path

    def launch(self):
        match get_os():
            case OS.WIN:
                self.__launch_windows()
            case OS.MAC:
                self.__launch_macos()
            case OS.LINUX:
                self.__launch_linux()

    def __validate_exec(self, exec_path):
        if exec_path is None or exec_path == 'None':
            msg = f'{self.name} path is not specified (None) for current Operating System! Update code and try again!'
            display_msg_box_ok('App Launcher', msg)
            return False
        elif not os.path.isfile(exec_path):
            msg = (f'{self.name} is not currently installed (Expected location: {exec_path}). '
                   f'Install first and try again!')
            display_msg_box_ok('App Launcher', msg)
            return False
        return True
    
    def __launch_windows(self):
        path_win_str = str(self.exec_path)

        if not self.__validate_exec(path_win_str):
            return

        if path_win_str.endswith('.ps1'):  # If powershell, run as powershell
            powerShellWrapper.exec_powershell(path_win_str)
        elif path_win_str.endswith('.cmd') or path_win_str.endswith('.bat'):  # If CMD, run in new window
            cwd = fileUtils.get_current_working_dir()
            ally_tools_temp_dir = str(Path(Path(cwd).parent, 'temp'))
            temp_file_path = str(Path(ally_tools_temp_dir, 'exec.bat'))
            print(f'App Launcher: Executing Temp Batch File: {temp_file_path}')
            cmdShellWrapper.exec_cmd(path_win_str, wait_for_output=False, in_new_window=temp_file_path)
        else:
            print('App Launcher: Executing Regular Launch')
            # subprocess.run([path_win_str], check=True, shell=True)
            cmdShellWrapper.exec_cmd(path_win_str, wait_for_output=False)

    def __launch_macos(self):

        path_macos_str = str(self.exec_path)

        if not self.__validate_exec(path_macos_str):
            return

        cmdShellWrapper.exec_cmd(path_macos_str, wait_for_output=False)

    def __launch_linux(self):
        path_linux_str = str(self.exec_path)

        if not self.__validate_exec(path_linux_str):
            return

        cmdShellWrapper.exec_cmd(path_linux_str, wait_for_output=False)  # TODO: TYPICAL COMMAND, SEE IF WORKS FOR OTHER STUFF (LIKE LAUNCHING APPS)
        # cmdShellWrapper.exec_cmd(["bash", path_linux_str], wait_for_output=True)  # TODO: For now this works for bash, but idk for other scenarios...


class StoreApp(App):
    def __init__(self, name, win_app_name: str):
        super().__init__(name)
        # Name of App Displayed on Request to PowerShell
        self.win_app_name = win_app_name

    def get_application_user_model_id(self) -> Union[str, None]:
        """
        Use this to get the application user model ID of an application from the Windows Store
        :param name: The expected Name of the Application
        """
        exec_cmd = 'Get-StartApps | Where-Object { $_.Name -like "*NAME*" }'.replace('*NAME*', f'*{self.win_app_name}*')
        print(f'Searching for {self.win_app_name}\'s Application User Model ID...')
        ps_output = powerShellWrapper.exec_powershell(exec_cmd)
        print(ps_output)
        for line in ps_output:
            if line.startswith(f'{self.win_app_name} '):
                aumid = line.split(' ')[-1]
                print(f'{self.name}\'s Application User Model ID Found!: {aumid}')
                return aumid
        error_msg = f'Could not recover Application User Model ID for: {self.name}. Install first and try again!'
        display_msg_box_ok('App Launcher', error_msg)
        return None

    def launch(self):
        op_sys = get_os()
        if op_sys == OS.WIN:
            aumid = self.get_application_user_model_id()
            if aumid is not None:
                os.system(f'explorer shell:appsFolder\\{aumid}')
        elif op_sys == OS.MAC:
            display_msg_box_ok('Store App Launcher', 'Windows Apps not supported on macOS')
        elif op_sys == OS.LINUX:
            display_msg_box_ok('Store App Launcher', 'Windows Apps not supported on Linux')


class Flatpak(App):
    def __init__(self, name: str, exec_path: Union[str, Path, None]):
        super().__init__(name)


class AppImage(App):
    def __init__(self, name: str, exec_path: Union[str, Path, None]):
        super().__init__(name)


def get_app_run_permissions(app_path: Path):
    """
    For macOS, gets the run permissions for a given .app by entering chmod +x in the terminal.
    """

    # Get Contents/MacOS path
    contents_macos_path = Path(app_path, 'Contents', 'MacOS')
    if not os.path.isdir(contents_macos_path):
        print('Can\'t get app run permissions, no Contents/MacOS sub folder!')
        return

    exec_path_lst = []
    # Figure out the exec list
    exec_path_lst = fileUtils.get_file_path_list(contents_macos_path)

    # For each exec list, apply permissions
    for exec_path in exec_path_lst:
        fileUtils.get_permission(exec_path)

