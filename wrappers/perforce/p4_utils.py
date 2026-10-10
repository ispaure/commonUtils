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
from typing import *
from pathlib import Path

# Blue Hole
from ...debugUtils import *
from ...wrappers import cmdShellWrapper
from ... import fileUtils
from ...osUtils import *
from .runtime import runtime
import os
import shlex
import subprocess

# ----------------------------------------------------------------------------------------------------------------------
# USER DEFINED VARIABLES

tool_name = 'Perforce Wrapper'
show_verbose = True

# ----------------------------------------------------------------------------------------------------------------------
# CODE


def p4_fstat_dict(file_path_string, silent_mode=False) -> Optional[List[Dict[str, str]]]:
    """
    Get p4 fstat results, cleaned as an array of dicts (1 dict per item)
    """

    # If file_path isn't enclosed in quotation marks, enclose.
    if '"' not in file_path_string[0]:
        file_path_string = '"' + file_path_string + '"'

    # Get status of files
    result_array = exec_p4_command("p4 fstat {}".format(file_path_string))

    result_dicts_lst = []
    result_dict = {}

    # Transform status of files in easily understood dict
    for i in result_array:
        if 'Your session has expired, please login again' in i:
            if not silent_mode:
                msg = 'Your session has expired. Please login again from Perforce. Aborting!'
                log(Severity.ERROR, tool_name, msg, popup=True)
            return None
        elif ' - no such file(s).' in i:
            result_dict = {'clientFile': i.replace(' - no such file(s).', '')}
            result_dicts_lst.append(result_dict)
            result_dict = {}
        elif ' - file(s) not in client view.' in i:
            result_dict = {'clientFile': i.replace(' - file(s) not in client view.', ''), 'notInClientView': True}
            result_dicts_lst.append(result_dict)
            result_dict = {}
        else:
            i = i.replace('... ', '')
            if len(i) > 0:
                split_i = i.split(' ')
                split_i_up_to_last = ''
                split_i_length = len(split_i)
                for idx, value in enumerate(split_i):
                    if idx > 0:
                        if idx < split_i_length - 1:
                            split_i_up_to_last += value + ' '
                        else:
                            split_i_up_to_last += value
                result_dict[split_i[0]] = split_i_up_to_last
            else:
                result_dicts_lst.append(result_dict)
                result_dict = {}

    if result_dict:
        result_dicts_lst.append(result_dict)
    return result_dicts_lst


def set_p4_env_settings():
    """Set only the environment overrides supplied by the application adapter."""
    for key, value in runtime().environment().items():
        if key not in ('P4USER', 'P4PORT', 'P4CLIENT'):
            raise ValueError(f'Unsupported Perforce environment key: {key}')
        setting = f'{key}={value}'
        quoted = subprocess.list2cmdline([setting]) if get_os() is OS.WIN else shlex.quote(setting)
        exec_p4_command('p4 set ' + quoted)


class P4UserWorkspace:
    def __init__(self):
        self.computername = None
        self.username = None
        self.workspace = None


def create_p4_user_workspace_cls(computer_name, username, workspace):
    p4userws_cls = P4UserWorkspace()
    p4userws_cls.computername = computer_name
    p4userws_cls.username = username
    p4userws_cls.workspace = workspace
    return p4userws_cls


def create_empty_binary_file(file_path):
    """Create a binary placeholder without replacing an existing file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    template = runtime().binary_template()
    if template is not None:
        fileUtils.File(template).copy_file(path)
    else:
        # A NUL byte keeps Perforce's auto-detection binary, matching BlueHole's template.
        with path.open('xb') as stream:
            stream.write(b'\x00')


def get_p4_macos_path() -> str:
    return str(runtime().executable(OS.MAC))


def get_p4_linux_path() -> str:
    return str(runtime().executable(OS.LINUX))


def exec_p4_command(command: str):
    """
    Execute Perforce commands. Based on cmdShellWrapper's exec_cmd,
    but with a few specific things to ensure proper functioning on macOS and Linux.
    """

    # Ensures this is used for Perforce commands, else raise exception and recommend using wrapper directly.
    if not command.startswith('p4 '):
        msg = (
            f'Perforce command execution failed.\n\n'
            f'What went wrong:\n'
            f'exec_p4_command can only execute Perforce commands that start with "p4 ". '
            f'Received: "{command}"\n\n'
            f'What to do:\n'
            f'Call cmdShellWrapper.exec_cmd for non-Perforce commands, or pass a valid Perforce command '
            f'(for example: "p4 info").'
        )
        log(Severity.CRITICAL, 'Perforce Command', msg)

    # Resolve P4 Path (macOS & Linux need to be pointed to p4_parallel file)
    p4_path: str = str(runtime().executable(get_os()))

    match get_os():
        case OS.MAC | OS.LINUX:
            # p4_parallel path needs to be valid
            if not os.path.isfile(p4_path):
                msg = (
                    f'Perforce command execution failed.\n\n'
                    f'What went wrong:\n'
                    f'The Perforce executable path is invalid:\n'
                    f'"{p4_path}"\n\n'
                    f'What to do:\n'
                    f'Ensure Perforce is installed and that the Perforce executable is available at the path above. '
                    f'If needed, configure the executable through commonUtils.wrappers.perforce.configure_runtime.\n\n'
                    f'Perforce operation aborted.'
                )
                log(Severity.CRITICAL, 'Perforce Command', msg)

            # Set permissions
            file_cls = fileUtils.File(Path(p4_path))
            file_cls.set_executable_permission()

            # Replace p4 in command with the path (in quotes)
            command = f'"{p4_path}"{command[2:]}'

    # Execute the command
    result = cmdShellWrapper.run_command(command, shell=True, idle_timeout=15)
    if result.timed_out or result.cancelled:
        # Partial output must not look like a completed Perforce operation.
        log(Severity.CRITICAL, 'Perforce Command', 'Perforce command timed out or was cancelled.')
    # fstat callers intentionally parse nonzero diagnostics such as "no such file(s)".
    # Keep their existing output-list contract while retaining an explicit outcome internally.
    if not result.success and not result.lines:
        log(Severity.CRITICAL, 'Perforce Command', f'Perforce exited with status {result.returncode}.')
    return result.lines
