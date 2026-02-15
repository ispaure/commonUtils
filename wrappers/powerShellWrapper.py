# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import subprocess

# Wrappers
from . import cmdShellWrapper


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
    else:
        # Use Regular CMD, but with Powershell script instead!
        # Add \ before " in command, as we'll need to put it in quotes in next step
        command_fixed = command.replace('"', '\\"')
        print(f'Sending command_fixed: {command_fixed}')
        return cmdShellWrapper.exec_cmd(f'powershell -NoProfile -Command "{command_fixed}"', wait_for_output=False)

