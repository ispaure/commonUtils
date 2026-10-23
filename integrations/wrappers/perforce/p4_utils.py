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
from ....runtime.diagnostics import *
from .. import cmdShellWrapper
from ....filesystem import files as fileUtils
from ....runtime.platform import *
from .runtime import runtime
import os
import subprocess
import stat

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

    # Keep the legacy preformatted-string entry point. Models pass path lists so
    # spaces and shell characters never need quoting or reparsing.
    if isinstance(file_path_string, str):
        if not file_path_string:
            return None
        if not file_path_string.startswith('"'):
            file_path_string = '"' + file_path_string + '"'
        result_array = exec_p4_command(f'p4 fstat {file_path_string}')
    else:
        paths = list(file_path_string)
        if not paths:
            return []
        outcome = exec_p4_arguments(['fstat', *paths], allow_fstat_diagnostics=True)
        if outcome.timed_out or outcome.cancelled:
            return None
        result_array = outcome.lines
        known_diagnostics = (' - no such file(s).', ' - file(s) not in client view.')
        if not outcome.success and not any(line.endswith(known_diagnostics) for line in result_array):
            log(Severity.ERROR, tool_name, f'Cannot read Perforce file status: {result_array}', popup=not silent_mode)
            return None

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
            if result_dict:
                result_dicts_lst.append(result_dict)
            result_dict = {'clientFile': i.replace(' - no such file(s).', '')}
            result_dicts_lst.append(result_dict)
            result_dict = {}
        elif ' - file(s) not in client view.' in i:
            if result_dict:
                result_dicts_lst.append(result_dict)
            result_dict = {'clientFile': i.replace(' - file(s) not in client view.', ''), 'notInClientView': True}
            result_dicts_lst.append(result_dict)
            result_dict = {}
        elif i.startswith('... '):
            key, separator, value = i[4:].partition(' ')
            if not key:
                return None
            result_dict[key] = value if separator else ''
        elif not i.strip():
            if result_dict:
                result_dicts_lst.append(result_dict)
            result_dict = {}
        else:
            log(Severity.ERROR, tool_name, f'Cannot read Perforce file status: {i}', popup=not silent_mode)
            return None

    if result_dict:
        result_dicts_lst.append(result_dict)
    if not result_dicts_lst:
        log(Severity.ERROR, tool_name, 'Perforce returned no file status records.', popup=not silent_mode)
        return None
    return result_dicts_lst


def set_p4_env_settings():
    """Set only the environment overrides supplied by the application adapter."""
    for key, value in runtime().environment().items():
        if key not in ('P4USER', 'P4PORT', 'P4CLIENT'):
            raise ValueError(f'Unsupported Perforce environment key: {key}')
        if not exec_p4_arguments(['set', f'{key}={value}']).success:
            return False
    return True


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


def exec_p4_arguments(arguments, *, allow_fstat_diagnostics=False):
    """Run separate CLI arguments and return a CommandResult, without a shell.

    Ordinary command failures are logged and returned so the host retains its
    save/export policy. Only fstat callers opt into parsing nonzero diagnostics.
    Timeout/cancellation never turns partial output into a completed operation.
    """
    if isinstance(arguments, (str, bytes)):
        raise TypeError('Supply Perforce arguments as a non-empty sequence')
    arguments = [os.fspath(argument) for argument in arguments]
    if not arguments:
        raise TypeError('Supply Perforce arguments as a non-empty sequence')
    executable = str(runtime().executable(get_os()))
    try:
        if get_os() in (OS.MAC, OS.LINUX):
            if not os.path.isfile(executable):
                raise FileNotFoundError(f'Perforce executable not found: {executable}')
            mode = os.stat(executable).st_mode
            if not mode & stat.S_IXUSR:
                os.chmod(executable, mode | stat.S_IXUSR)
        result = cmdShellWrapper.run_command([executable, *arguments], idle_timeout=15)
    except OSError as error:
        result = cmdShellWrapper.CommandResult(None, stderr=(str(error),))
    if not result.success and (not allow_fstat_diagnostics or result.timed_out or result.cancelled):
        reason = ('timed out' if result.timed_out else 'was cancelled' if result.cancelled
                  else f'failed (exit status {result.returncode})')
        details = '\n'.join(result.lines)
        log(Severity.ERROR, tool_name,
            f'Perforce {arguments[0]} {reason}.\nArguments: {arguments[1:]!r}\n{details}')
    return result


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
                    f'If needed, configure the executable through commonUtils.integrations.wrappers.perforce.configure_runtime.\n\n'
                    f'Perforce operation aborted.'
                )
                log(Severity.CRITICAL, 'Perforce Command', msg)

            # Set permissions
            file_cls = fileUtils.File(Path(p4_path))
            file_cls.set_executable_permission()

            # Replace p4 in command with the path (in quotes)
            command = f'"{p4_path}"{command[2:]}'

        case OS.WIN:
            command = subprocess.list2cmdline([p4_path]) + command[2:]

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
