from commonUtils.wrappers import cmdShellWrapper
from commonUtils.pySideUtils import *
from commonUtils.wrappers import powerShellWrapper
import os
from typing import *
import os
from commonUtils import fileUtils
from pathlib import Path
import subprocess
from commonUtils.pySideUtils import *


class App:
    def __init__(self, name):
        self.name = name


class DiskApp(App):
    def __init__(self, name, path_win: Union[str, Path, None], path_mac: Union[str, Path, None] = None):
        super().__init__(name)
        self.path_win = path_win
        self.path_mac = path_mac

    def launch(self):
        resolved_path = self.path_win
        if resolved_path is None:
            msg = f'{self.name} is not currently installed. Install first and try again!'
            display_msg_box_ok('App Launcher', msg)
        elif not os.path.isfile(resolved_path):
            msg = f'{self.name} is not currently installed. Install first and try again!'
            display_msg_box_ok('App Launcher', msg)
        elif resolved_path.endswith('.ps1'):  # If powershell, run as powershell
            powerShellWrapper.exec_powershell(resolved_path)
        elif resolved_path.endswith('.cmd') or resolved_path.endswith('.bat'):  # If CMD, run in new window
            cwd = fileUtils.get_current_working_dir()
            ally_tools_temp_dir = str(Path(Path(cwd).parent, 'temp'))
            temp_file_path = str(Path(ally_tools_temp_dir, 'exec.bat'))
            print(f'executing custom temp file path script: {temp_file_path}')
            cmdShellWrapper.exec_cmd(resolved_path, wait_for_output=False, in_new_window=temp_file_path)
        else:
            print('Regular Launch')
            # subprocess.run([resolved_path], check=True, shell=True)
            cmdShellWrapper.exec_cmd(resolved_path, wait_for_output=False)


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
        op_sys = fileUtils.get_os()
        if op_sys == 'Windows':
            aumid = self.get_application_user_model_id()
            if aumid is not None:
                os.system(f'explorer shell:appsFolder\\{aumid}')
        elif op_sys == 'macOS':
            display_msg_box_ok('Store App Launcher', 'Windows Apps not supported on macOS')
        elif op_sys == 'Linux':
            display_msg_box_ok('Store App Launcher', 'Windows Apps not supported on Linux')
