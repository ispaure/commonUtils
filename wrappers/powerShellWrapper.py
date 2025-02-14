from typing import *
import os
import subprocess
import ctypes

# Common utilities
from commonUtils import debugUtils

# Wrappers
from commonUtils.wrappers import cmdShellWrapper


def exec_powershell(command, wait_for_output=True):
    if wait_for_output is True:
        # Run the command
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-Command", command],
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

