from typing import *
from pathlib import Path
import os
import subprocess
import time
import shlex

# Common utilities
import commonUtils.fileUtils as fileUtils
from commonUtils import debugUtils
from commonUtils.osUtils import *


tool_name = 'commonUtils/cmdShellWrapper.py'


def delete_script_file(file_path):
    # Delete script file if exists. Returns false if could not delete
    if os.path.exists(file_path):
        os.remove(file_path)
        if os.path.exists(file_path):
            print('Could not remove properly, do NOT continue with sync')
            return False
    return True


def should_use_shell(command):
    """Decide whether to use shell=True based on command and OS"""
    if get_os() == OS.WIN or get_os() == OS.MAC:  # TODO: Added macOS back here to patch up, idk if want this!
        return True  # Windows prefers shell=True for most cases
    elif isinstance(command, list):
        return False  # List commands always work with shell=False
    elif any(symbol in command for symbol in ["|", ">", "&", ";"]):
        return True  # Linux/macOS shell syntax requires shell=True
    else:
        return False


def exec_cmd(command: str,
             wait_for_output: bool = True,
             in_new_window: bool = False):
    """
    Execute command from CMD shell (Windows) or the terminal (MacOS & Linux)

    Notes:
    - If in_new_window=True, command is launched in a new terminal window and THIS FUNCTION RETURNS IMMEDIATELY.
      (No output capture in the parent process.)
    - For simplicity right now, shell=True is always used (per your request).
    """

    def terminate_p_open(p_open_to_close):
        """
        Close Popen subprocess
        :param p_open_to_close: Popen to close
        :type p_open_to_close: subprocess.Popen
        """
        try:
            if p_open_to_close.stderr:
                p_open_to_close.stderr.close()
        except Exception:
            pass
        try:
            if p_open_to_close.stdout:
                p_open_to_close.stdout.close()
        except Exception:
            pass
        try:
            if p_open_to_close.stdin is not None:
                p_open_to_close.stdin.close()
        except Exception:
            pass

    def clean_output_line(line_str: bytes) -> str:
        """
        Clean output lines so they only keep relevant information.
        """
        decoded_line = line_str.decode(errors="replace")
        cleaned_line = decoded_line.rstrip('\n').rstrip('\r')

        debugUtils.log(debugUtils.Severity.DEBUG, 'cmdShellWrapper', cleaned_line)
        return cleaned_line

    def pick_linux_terminal() -> Optional[str]:
        """
        Prefer terminals that exist on the system.
        """
        for term in ("konsole", "gnome-terminal", "xterm"):
            if shutil.which(term):
                return term
        return None

    # Log command to execute
    debugUtils.log(debugUtils.Severity.DEBUG, tool_name, f'Executing command: {command}')

    # If code must be executed in new terminal window
    if in_new_window:
        # You said: if launching in new window, you never need to wait for output.
        # Force no-wait behavior and return immediately after launch.
        wait_for_output = False

        match get_os():
            case OS.WIN:
                # Keep window open after completion:
                # - start "" ... : empty title required when the next token is quoted
                # - cmd.exe /k   : keep window open
                #
                # We wrap your original command in a new cmd window that stays open.
                # shell=True is assumed globally right now.
                #
                # NOTE: If your command already includes its own quotes, that’s fine.
                new_window_cmd = f'cmd.exe /c start "" cmd.exe /k {command}'

            case OS.LINUX:
                term = pick_linux_terminal()
                if not term:
                    debugUtils.log(
                        debugUtils.Severity.CRITICAL,
                        tool_name,
                        "No supported terminal found (konsole/gnome-terminal/xterm)."
                    )
                    return False

                # Run like a terminal command and keep the window open.
                # We quote the entire command as a single bash -lc argument.
                bash_lc_arg = shlex.quote(command)

                if term == "konsole":
                    # --hold keeps window open after command finishes
                    new_window_cmd = f'konsole --hold -e bash -lc {bash_lc_arg}'
                elif term == "gnome-terminal":
                    # exec bash keeps it open after command completes
                    # (bash -lc runs the command; then we run an interactive bash)
                    new_window_cmd = f'gnome-terminal -- bash -lc {shlex.quote(command + "; exec bash")}'
                else:
                    # xterm -hold keeps window open
                    new_window_cmd = f'xterm -hold -e bash -lc {bash_lc_arg}'

            case OS.MAC:
                # Run command via bash, then keep terminal open
                bash_cmd = f"bash -lc {shlex.quote(command + '; exec bash')}"

                # Escape for AppleScript string literal (double quotes and backslashes)
                applescript_cmd = bash_cmd.replace("\\", "\\\\").replace('"', '\\"')

                applescript = (
                    'tell application "Terminal"\n'
                    '  activate\n'
                    f'  do script "{applescript_cmd}"\n'
                    'end tell'
                )

                subprocess.Popen(["osascript", "-e", applescript], stdin=None)
                return []

            case _:
                debugUtils.log(debugUtils.Severity.CRITICAL, tool_name, 'Platform not supported!')
                return False

        debugUtils.log(debugUtils.Severity.DEBUG, tool_name, f'Launching in new window: {new_window_cmd}')

        # For simplicity right now: always shell=True
        try:
            subprocess.Popen(new_window_cmd, shell=True, stdin=None)
            return []  # launched; no output captured
        except Exception as e:
            debugUtils.log(debugUtils.Severity.CRITICAL, tool_name, f'Failed to launch in new window: {e}')
            return False

    # --- Normal (same-window) execution path ---

    # Time out value (in seconds) — your comment said ms, but time.time() is seconds.
    time_out = 15

    # Should use shell?
    # use_shell = should_use_shell(command)
    use_shell = True  # per your request for now

    # Open subprocess
    p_open = subprocess.Popen(
        command,
        shell=use_shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=None
    )

    output_lines: list[bytes] = []
    loop_begin_time = time.time()
    stdout_lst: list[bytes] = []
    stderr_lst: list[bytes] = []

    if wait_for_output:
        while True:
            status = p_open.poll()
            if p_open.stdout:
                try:
                    p_open.stdout.flush()
                except Exception:
                    pass

            stdout = p_open.stdout.readlines() if p_open.stdout else []
            stderr = p_open.stderr.readlines() if p_open.stderr else []

            if stdout:
                stdout_lst += stdout
            if stderr:
                stderr_lst += stderr

            if stdout or stderr:
                loop_begin_time = time.time()

            if status is not None:
                output_lines = stdout_lst + stderr_lst
                terminate_p_open(p_open)
                break

            if (time.time() - loop_begin_time) > time_out:
                terminate_p_open(p_open)
                break

    # Clean the output lines
    output_lines_cleaned: list[str] = []
    for line in output_lines:
        output_lines_cleaned.append(clean_output_line(line))

    return output_lines_cleaned
