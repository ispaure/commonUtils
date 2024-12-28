from commonUtils.wrappers import cmdShellWrapper
from commonUtils.pySideUtils import *
from commonUtils.wrappers import powerShellWrapper
import os
from typing import *
import os
from commonUtils import fileUtils
from pathlib import Path


class App:
    def __init__(self, name):
        self.name = name


class DiskApp(App):
    def __init__(self, name, disk_path: Union[str, None] = None):
        super().__init__(name)
        self.disk_path = disk_path

    def __get_resolved_path(self):
        """
        Get disk path properly (if there's a question mark as first char, don't know which drive it's in)
        """
        if self.disk_path.startswith('%SOFTWARE%'):
            cwd = fileUtils.get_current_working_dir()
            print('Resolving Path with CurrentWorkingDirectory...')
            print(f'Path to resolve: {self.disk_path}')
            if str(cwd).endswith('Python'):
                ally_tools_root = str(Path(Path(cwd).parent, 'Software'))
            else:
                ally_tools_root = str(Path(cwd, 'Software'))
            resolved_path = self.disk_path.replace('%SOFTWARE%', ally_tools_root)
            print(f'Resolved path: {resolved_path}')
            return resolved_path
        if self.disk_path.startswith('?'):
            alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            for char in alphabet:
                attempted_path = f'{char}{self.disk_path[1:]}'
                if os.path.isfile(attempted_path):
                    return attempted_path
            return None
        else:
            return os.path.expandvars(self.disk_path)


    def launch(self):
        resolved_path = self.__get_resolved_path()
        if resolved_path is None:
            msg = f'{self.name} is not currently installed on this ROG Ally. Install first and try again!'
            display_msg_box_ok('App Launcher', msg)
        elif not os.path.isfile(resolved_path):
            msg = f'{self.name} is not currently installed on this ROG Ally. Install first and try again!'
            display_msg_box_ok('App Launcher', msg)
        elif resolved_path.endswith('.ps1'):  # If powershell, run as powershell
            powerShellWrapper.exec_powershell(resolved_path)
        else:
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
        aumid = self.get_application_user_model_id()
        if aumid is not None:
            os.system(f'explorer shell:appsFolder\\{aumid}')
