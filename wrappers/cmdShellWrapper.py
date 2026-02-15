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
import subprocess
import time
import shlex
import shutil

# Common utilities
from .. import debugUtils
from ..osUtils import *


# ----------------------------------------------------------------------------------------------------------------------
# CODE

tool_name = 'commonUtils/cmdShellWrapper.py'


def exec_cmd(command: str,
             wait_for_output: bool = True,
             in_new_window: bool = False,
             time_out: float = 15):
    """
    Execute command from CMD shell (Windows) or the terminal (macOS & Linux)

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

    # ------------------------------
    # Linux terminal helpers (UPDATED)
    # ------------------------------

    def pick_linux_terminal() -> Optional[str]:
        """
        Prefer terminals that exist on the system.

        - Respects $TERMINAL if set.
        - Detects KDE vs GNOME and prefers a likely default.
        - Includes common modern terminals that may exist on Fedora/Bazzite.
        """
        # 1) Respect user preference if set
        env_term = os.environ.get("TERMINAL")
        if env_term:
            # TERMINAL might include args; take the binary part
            bin_name = env_term.split()[0]
            if shutil.which(bin_name):
                return bin_name

        # 2) Desktop-session hints (KDE vs GNOME)
        desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
        session = (os.environ.get("DESKTOP_SESSION") or "").lower()
        prefer_kde = ("kde" in desktop) or ("plasma" in desktop) or ("kde" in session) or ("plasma" in session)

        # 3) Candidate lists
        kde_first = ["konsole"]
        gnome_first = ["kgx", "gnome-terminal", "ptyxis"]  # kgx = GNOME Console
        common = [
            "xterm",
            "kitty",
            "alacritty",
            "wezterm",
            "footclient",
            "tilix",
            "xfce4-terminal",
            "lxterminal",
            "mate-terminal",
            "ptyxis",
        ]

        candidates = (kde_first + gnome_first + common) if prefer_kde else (gnome_first + kde_first + common)

        for term in candidates:
            if shutil.which(term):
                return term
        return None

    def build_linux_new_window_cmd(term: str, command: str) -> str:
        """
        Build a shell command (string) that opens a new terminal window
        and keeps it open after the command runs.

        Uses bash -lc so the command behaves like a normal terminal command.
        """
        bash_lc_arg = shlex.quote(command)

        # KDE Konsole
        if term == "konsole":
            return f'konsole --hold -e bash -lc {bash_lc_arg}'

        # GNOME terminals
        if term in ("gnome-terminal", "kgx"):
            # Run the command, then keep the terminal open with an interactive bash
            return f'{term} -- bash -lc {shlex.quote(command + "; exec bash")}'

        # Ptyxis (often present on Fedora/Bazzite)
        if term == "ptyxis":
            # Similar semantics: run command then keep open with exec bash
            # Using "--" to separate ptyxis args from the command.
            return f'ptyxis -- bash -lc {shlex.quote(command + "; exec bash")}'

        # XTerm
        if term == "xterm":
            return f'xterm -hold -e bash -lc {bash_lc_arg}'

        # XFCE terminal
        if term == "xfce4-terminal":
            # xfce4-terminal supports --hold on many versions; even if not, exec bash keeps it open
            return f'xfce4-terminal --hold -e bash -lc {shlex.quote(command + "; exec bash")}'

        # Kitty
        if term == "kitty":
            return f'kitty bash -lc {shlex.quote(command + "; exec bash")}'

        # Alacritty
        if term == "alacritty":
            return f'alacritty -e bash -lc {shlex.quote(command + "; exec bash")}'

        # WezTerm
        if term == "wezterm":
            return f'wezterm start -- bash -lc {shlex.quote(command + "; exec bash")}'

        # Foot (Wayland)
        if term == "footclient":
            return f'footclient bash -lc {shlex.quote(command + "; exec bash")}'

        # Generic fallback: try "-e" which many terminals support
        return f'{term} -e bash -lc {shlex.quote(command + "; exec bash")}'

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
                new_window_cmd = f'cmd.exe /c start "" cmd.exe /k "{command}"'

            case OS.LINUX:
                term = pick_linux_terminal()
                if not term:
                    debugUtils.log(
                        debugUtils.Severity.CRITICAL,
                        tool_name,
                        "No supported terminal found (konsole/kgx/gnome-terminal/ptyxis/xterm/kitty/alacritty/wezterm/footclient...)."
                    )
                    return False

                new_window_cmd = build_linux_new_window_cmd(term, command)

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
