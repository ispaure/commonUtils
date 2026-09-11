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
import queue
import subprocess
import threading
import time

from ... import debugUtils
from . import output
from . import process
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
    """Execute a command while capturing output and enforcing an idle-output timeout."""
    command_process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=None,
        cwd=cwd,
        **process.get_process_group_kwargs()
    )

    output_queue = queue.Queue()
    stdout_output = bytearray()
    stderr_output = bytearray()

    stdout_thread = threading.Thread(
        target=output.read_stream,
        args=(command_process.stdout, 'stdout', output_queue),
        daemon=True
    )
    stderr_thread = threading.Thread(
        target=output.read_stream,
        args=(command_process.stderr, 'stderr', output_queue),
        daemon=True
    )

    stdout_thread.start()
    stderr_thread.start()

    active_streams = 2
    last_output_time = time.monotonic()
    timed_out = False

    while active_streams > 0:
        idle_time = time.monotonic() - last_output_time

        if idle_time > time_out:
            timed_out = True
            break

        remaining_time = max(0.01, min(0.1, time_out - idle_time))

        try:
            stream_name, chunk = output_queue.get(timeout=remaining_time)
        except queue.Empty:
            continue

        if chunk is None:
            active_streams -= 1
            continue

        last_output_time = time.monotonic()

        if stream_name == 'stdout':
            stdout_output.extend(chunk)
        else:
            stderr_output.extend(chunk)

    if timed_out:
        msg = f'Command exceeded idle timeout of {time_out} seconds and will be terminated.'
        debugUtils.log(debugUtils.Severity.WARNING, tool_name, msg)
        process.terminate_process_tree(command_process)
    else:
        command_process.wait()
        process.close_process_streams(command_process)

    # Give reader threads a chance to finish after the process and its streams have been closed.
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)

    # Drain output captured immediately before the process or streams were closed.
    output.drain_output_queue(output_queue, stdout_output, stderr_output)

    # Preserve the previous return behavior: stdout first, followed by stderr.
    stdout_lines = output.output_bytes_to_lines(bytes(stdout_output))
    stderr_lines = output.output_bytes_to_lines(bytes(stderr_output))
    output_lines = stdout_lines + stderr_lines

    return [output.clean_output_line(line) for line in output_lines]