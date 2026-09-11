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

from typing import *
from pathlib import Path
import os
import queue
import shlex
import shutil
import signal
import subprocess
import threading
import time

# Common utilities
from .. import debugUtils
from ..osUtils import *


# ----------------------------------------------------------------------------------------------------------------------
# CODE

tool_name = 'commonUtils/wrappers/cmdShellWrapper.py'


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

    # Normalize working directory
    cwd = str(cwd) if cwd is not None else None

    def close_process_streams(process: subprocess.Popen):
        """Close any open streams belonging to a subprocess."""
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass

    def terminate_process_tree(process: subprocess.Popen):
        """
        Terminate the subprocess and its child process tree.

        Commands are launched in their own process group/session when waiting for output so a timeout can terminate the
        shell and any child processes that were started by it.
        """
        match get_os():
            case OS.WIN:
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

            case OS.MAC | OS.LINUX:
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

    def clean_output_line(line_str: bytes) -> str:
        """Clean an output line so it only keeps relevant information."""
        decoded_line = line_str.decode(errors='replace')
        cleaned_line = decoded_line.rstrip('\n').rstrip('\r')

        debugUtils.log(debugUtils.Severity.DEBUG, tool_name, cleaned_line)
        return cleaned_line

    def output_bytes_to_lines(output: bytes) -> list[bytes]:
        """
        Convert captured output bytes into lines while preserving the previous newline-based behavior.

        Carriage returns embedded within a line are preserved. A trailing newline does not create an additional empty
        output entry.
        """
        if not output:
            return []

        lines = output.split(b'\n')

        if lines[-1] == b'':
            lines.pop()

        return lines

    # ------------------------------
    # Linux terminal helpers
    # ------------------------------

    def pick_linux_terminal() -> Optional[str]:
        """
        Prefer terminals that exist on the system.

        - Respects $TERMINAL if set.
        - Detects KDE vs GNOME and prefers a likely default.
        - Includes common modern terminals that may exist on Fedora/Bazzite.
        """

        # 1) Respect user preference if set
        env_term = os.environ.get('TERMINAL')
        if env_term:
            # TERMINAL might include args; take the binary part
            bin_name = env_term.split()[0]
            if shutil.which(bin_name):
                return bin_name

        # 2) Desktop-session hints (KDE vs GNOME)
        desktop = (os.environ.get('XDG_CURRENT_DESKTOP') or '').lower()
        session = (os.environ.get('DESKTOP_SESSION') or '').lower()
        prefer_kde = ('kde' in desktop) or ('plasma' in desktop) or ('kde' in session) or ('plasma' in session)

        # 3) Candidate lists
        kde_first = ['konsole']
        gnome_first = ['kgx', 'gnome-terminal', 'ptyxis']
        common = [
            'xterm',
            'kitty',
            'alacritty',
            'wezterm',
            'footclient',
            'tilix',
            'xfce4-terminal',
            'lxterminal',
            'mate-terminal',
        ]

        candidates = (kde_first + gnome_first + common) if prefer_kde else (gnome_first + kde_first + common)

        for term in candidates:
            if shutil.which(term):
                return term

        return None

    def build_linux_new_window_cmd(term: str, command_to_run: str) -> str:
        """
        Build a shell command that opens a new terminal window and keeps it open after the command runs.

        Uses bash -lc so the command behaves like a normal terminal command.
        """
        bash_lc_arg = shlex.quote(command_to_run)

        # KDE Konsole
        if term == 'konsole':
            return f'konsole --hold -e bash -lc {bash_lc_arg}'

        # GNOME terminals
        if term in ('gnome-terminal', 'kgx'):
            return f'{term} -- bash -lc {shlex.quote(command_to_run + "; exec bash")}'

        # Ptyxis (often present on Fedora/Bazzite)
        if term == 'ptyxis':
            return f'ptyxis -- bash -lc {shlex.quote(command_to_run + "; exec bash")}'

        # XTerm
        if term == 'xterm':
            return f'xterm -hold -e bash -lc {bash_lc_arg}'

        # XFCE terminal
        if term == 'xfce4-terminal':
            return f'xfce4-terminal --hold -e bash -lc {shlex.quote(command_to_run + "; exec bash")}'

        # Kitty
        if term == 'kitty':
            return f'kitty bash -lc {shlex.quote(command_to_run + "; exec bash")}'

        # Alacritty
        if term == 'alacritty':
            return f'alacritty -e bash -lc {shlex.quote(command_to_run + "; exec bash")}'

        # WezTerm
        if term == 'wezterm':
            return f'wezterm start -- bash -lc {shlex.quote(command_to_run + "; exec bash")}'

        # Foot (Wayland)
        if term == 'footclient':
            return f'footclient bash -lc {shlex.quote(command_to_run + "; exec bash")}'

        # Generic fallback: try "-e" which many terminals support
        return f'{term} -e bash -lc {shlex.quote(command_to_run + "; exec bash")}'

    # Log command to execute
    debugUtils.log(debugUtils.Severity.DEBUG, tool_name, f'Executing command: {command}')

    if cwd is not None:
        debugUtils.log(debugUtils.Severity.DEBUG, tool_name, f'Working directory: {cwd}')

    # ------------------------------
    # New terminal window
    # ------------------------------

    if in_new_window:
        match get_os():
            case OS.WIN:
                # Keep window open after completion:
                # - start "" ... : empty title required when the next token is quoted
                # - cmd.exe /k   : keep window open
                new_window_cmd = f'cmd.exe /c start "" cmd.exe /k "{command}"'

            case OS.LINUX:
                term = pick_linux_terminal()

                if not term:
                    msg = (
                        'No supported terminal found '
                        '(konsole/kgx/gnome-terminal/ptyxis/xterm/kitty/alacritty/wezterm/footclient...).'
                    )
                    debugUtils.log(debugUtils.Severity.CRITICAL, tool_name, msg)
                    return False

                new_window_cmd = build_linux_new_window_cmd(term, command)

            case OS.MAC:
                # Terminal.app creates the shell itself, so setting cwd on the
                # osascript process is not sufficient. Explicitly cd instead.
                terminal_command = command

                if cwd is not None:
                    terminal_command = f'cd {shlex.quote(cwd)} && {terminal_command}'

                # Run command via bash, then keep Terminal open
                bash_cmd = f"bash -lc {shlex.quote(terminal_command + '; exec bash')}"

                # Escape for AppleScript string literal
                applescript_cmd = bash_cmd.replace('\\', '\\\\').replace('"', '\\"')

                applescript = (
                    'tell application "Terminal"\n'
                    '  activate\n'
                    f'  do script "{applescript_cmd}"\n'
                    'end tell'
                )

                subprocess.Popen(['osascript', '-e', applescript], stdin=None)
                return []

            case _:
                debugUtils.log(debugUtils.Severity.CRITICAL, tool_name, 'Platform not supported!')
                return False

        debugUtils.log(debugUtils.Severity.DEBUG, tool_name, f'Launching in new window: {new_window_cmd}')

        try:
            subprocess.Popen(new_window_cmd, shell=True, stdin=None, cwd=cwd)
            return []
        except Exception as e:
            debugUtils.log(debugUtils.Severity.CRITICAL, tool_name, f'Failed to launch in new window: {e}')
            return False

    # ------------------------------
    # Normal (same-window) execution
    # ------------------------------

    # Commands whose output is not needed do not require pipes. Using DEVNULL also prevents an unconsumed pipe from
    # filling up and blocking a long-running child process.
    if not wait_for_output:
        subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=None,
            cwd=cwd
        )
        return []

    # Commands whose output is monitored are placed in their own process group/session. This allows the entire command
    # tree to be terminated if the idle timeout is exceeded.
    process_kwargs = {}

    match get_os():
        case OS.WIN:
            process_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

        case OS.MAC | OS.LINUX:
            process_kwargs['start_new_session'] = True

    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=None,
        cwd=cwd,
        **process_kwargs
    )

    output_queue = queue.Queue()
    stdout_output = bytearray()
    stderr_output = bytearray()

    def read_stream(stream, stream_name: str):
        """
        Read binary chunks from a subprocess stream.

        Reading chunks instead of complete lines ensures output such as progress updates using carriage returns or
        partial writes still counts as activity and resets the idle timeout.
        """
        try:
            while True:
                if hasattr(stream, 'read1'):
                    chunk = stream.read1(4096)
                else:
                    chunk = stream.read(4096)

                if not chunk:
                    break

                output_queue.put((stream_name, chunk))

        except (OSError, ValueError):
            # The stream may be closed by timeout handling while this reader is blocked.
            pass

        finally:
            output_queue.put((stream_name, None))

    stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, 'stdout'), daemon=True)
    stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, 'stderr'), daemon=True)

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
        terminate_process_tree(process)
    else:
        process.wait()
        close_process_streams(process)

    # Give reader threads a chance to finish after the process and its streams have been closed.
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)

    # Drain output captured immediately before the process or streams were closed.
    while True:
        try:
            stream_name, chunk = output_queue.get_nowait()
        except queue.Empty:
            break

        if chunk is None:
            continue

        if stream_name == 'stdout':
            stdout_output.extend(chunk)
        else:
            stderr_output.extend(chunk)

    # Preserve the previous return behavior: stdout first, followed by stderr.
    stdout_lines = output_bytes_to_lines(bytes(stdout_output))
    stderr_lines = output_bytes_to_lines(bytes(stderr_output))
    output_lines = stdout_lines + stderr_lines

    return [clean_output_line(line) for line in output_lines]


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
