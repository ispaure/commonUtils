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

import os
import signal
import subprocess

from ... import debugUtils
from ...osUtils import OS, get_os


# ----------------------------------------------------------------------------------------------------------------------
# CODE

tool_name = 'commonUtils/wrappers/cmdShellWrapper'


def get_process_group_kwargs() -> dict:
    """
    Return platform-specific Popen arguments that place the command in its own process group/session.

    This allows timeout handling to terminate both the shell and child processes started by it.
    """
    match get_os():
        case OS.WIN:
            return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}

        case OS.MAC | OS.LINUX:
            return {'start_new_session': True}

        case _:
            return {}


def terminate_process_tree(process: subprocess.Popen):
    """Terminate the subprocess and its child process tree."""
    match get_os():
        case OS.WIN:
            _terminate_process_tree_windows(process)

        case OS.MAC | OS.LINUX:
            _terminate_process_tree_unix(process)

        case _:
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except Exception:
                    pass
            except Exception:
                pass

    close_process_streams(process)


def _terminate_process_tree_windows(process: subprocess.Popen):
    """Terminate a Windows process tree using taskkill."""
    # taskkill /T targets the entire process tree rather than only the shell created by shell=True.
    try:
        subprocess.run(
            ['taskkill', '/PID', str(process.pid), '/T'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2
        )
    except Exception:
        pass

    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            subprocess.run(
                ['taskkill', '/F', '/PID', str(process.pid), '/T'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2
            )
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
    except Exception:
        pass


def _terminate_process_tree_unix(process: subprocess.Popen):
    """Terminate a macOS/Linux process group using SIGTERM followed by SIGKILL if required."""
    # start_new_session=True makes the process PID the process-group ID.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception:
        try:
            process.terminate()
        except Exception:
            pass

    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
    except Exception:
        pass


def close_process_streams(process: subprocess.Popen):
    """Close any open streams belonging to a subprocess."""
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


def minimize_console_window() -> bool:
    """Minimize the active process's terminal window (currently only works on Windows)."""
    # TODO: Make Minimize Console Window work on macOS & Linux
    match get_os():
        case OS.WIN:
            import ctypes

            handle = ctypes.windll.kernel32.GetConsoleWindow()
            ctypes.windll.user32.ShowWindow(handle, 6)
            return True

        case OS.MAC | OS.LINUX:
            title = 'commonUtils.wrappers.cmdShellWrapper.minimize_console_window'
            msg = (
                'Minimize Console Window has only been implemented for Windows so far. Please update '
                'cmdShellWrapper with the cross-platform branches.'
            )
            debugUtils.log(debugUtils.Severity.WARNING, title, msg)

    return False