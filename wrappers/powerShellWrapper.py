from commonUtils.wrappers import cmdShellWrapper
from typing import *
import subprocess
from commonUtils import debugUtils
import ctypes
import os


def exec_powershell(command, wait_for_output=True):
    if wait_for_output is True:
        # Run the command
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, shell=False
        )

        # Check output and errors
        if result.returncode == 0:
            return result.stdout.splitlines()
        else:
            print("Error:\n", result.stderr)
            debugUtils.exit_msg('Critical Failure!')
    else:
        # Use Regular CMD, but with Powershell script instead!
        # Add \ before " in command, as we'll need to put it in quotes in next step
        command_fixed = command.replace('"', '\\"')
        print(f'Sending command_fixed: {command_fixed}')
        return cmdShellWrapper.exec_cmd(f'powershell -NoProfile -Command "{command_fixed}"', wait_for_output=False)


def get_application_user_model_id(name: str) -> str:
    """
    Use this to get the application user model ID of an application from the Windows Store
    :param name: The expected Name of the Application
    """
    exec_cmd = 'Get-StartApps | Where-Object { $_.Name -like "*NAME*" }'.replace('*NAME*', f'*{name}*')
    print(f'Searching for {name}\'s Application User Model ID...')
    ps_output = exec_powershell(exec_cmd)
    print(ps_output)
    for line in ps_output:
        if line.startswith(f'{name} '):
            aumid = line.split(' ')[-1]
            print(f'{name}\'s Application User Model ID Found!: {aumid}')
            return aumid


def launch_application_from_user_model_id(aumid: str):
    os.system(f'explorer shell:appsFolder\\{aumid}')
