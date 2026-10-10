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

from pathlib import Path
from typing import Optional, Union
import subprocess

from ... import debugUtils
from . import output
from .result import run_command
from . import terminal


# ----------------------------------------------------------------------------------------------------------------------
# CODE

tool_name = 'commonUtils/wrappers/cmdShellWrapper'


def exec_cmd(command: str,
             wait_for_output: bool = True,
             in_new_window: bool = False,
             time_out: float = 15,
             cwd: Optional[Union[str, Path]] = None):
    """
    Execute command from CMD shell (Windows) or the terminal (macOS & Linux).

    :param command: Command to execute.
    :param wait_for_output: Whether to wait for and capture command output.
    :param in_new_window: Whether to execute the command in a new terminal window.
    :param time_out: Maximum amount of idle time to wait without receiving output.
    :param cwd: Working directory in which the command should execute.

    Notes:
    - If in_new_window=True, command is launched in a new terminal window and THIS FUNCTION RETURNS IMMEDIATELY.
      No output is captured in the parent process.
    - time_out is an idle-output timeout, not a maximum command runtime. A command can run indefinitely as long as
      stdout or stderr continues producing output.
    - For simplicity right now, shell=True is always used for normal command execution.
    """
    cwd = str(cwd) if cwd is not None else None

    debugUtils.log(debugUtils.Severity.DEBUG, tool_name, f'Executing command: {command}')

    if cwd is not None:
        debugUtils.log(debugUtils.Severity.DEBUG, tool_name, f'Working directory: {cwd}')

    if in_new_window:
        return terminal.exec_cmd_new_window(command, cwd)

    if not wait_for_output:
        return _exec_cmd_no_output(command, cwd)

    return _exec_cmd_with_output(command, time_out, cwd)


def _exec_cmd_no_output(command: str, cwd: Optional[str]):
    """Launch a command without waiting for or capturing its output."""
    # DEVNULL prevents an unconsumed pipe from filling up and blocking a long-running child process.
    subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=None,
        cwd=cwd
    )
    return []


def _exec_cmd_with_output(command: str, time_out: float, cwd: Optional[str]):
    """Compatibility API: stdout/stderr lines, retaining the historical idle timeout."""
    result = run_command(command, cwd=cwd, idle_timeout=time_out, shell=True, stdin=None)
    if result.timed_out:
        debugUtils.log(debugUtils.Severity.WARNING, tool_name,
                       f'Command exceeded idle timeout of {time_out} seconds and was terminated.')
    return [output.clean_output_line(line.encode('utf-8')) for line in result.lines]
