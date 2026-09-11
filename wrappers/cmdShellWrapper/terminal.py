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

from typing import Optional
import os
import shlex
import shutil
import subprocess

from ... import debugUtils
from ...osUtils import OS, get_os


# ----------------------------------------------------------------------------------------------------------------------
# CODE

tool_name = 'commonUtils/wrappers/cmdShellWrapper'


def exec_cmd_new_window(command: str, cwd: Optional[str]):
    """Launch a command in a new terminal window and return immediately."""
    match get_os():
        case OS.WIN:
            return _exec_cmd_new_window_windows(command, cwd)

        case OS.MAC:
            return _exec_cmd_new_window_macos(command, cwd)

        case OS.LINUX:
            return _exec_cmd_new_window_linux(command, cwd)

        case _:
            debugUtils.log(debugUtils.Severity.CRITICAL, tool_name, 'Platform not supported!')
            return False


def _exec_cmd_new_window_windows(command: str, cwd: Optional[str]):
    """Launch a command in a new Windows CMD window and keep the window open."""
    # - start "" ... : empty title required when the next token is quoted
    # - cmd.exe /k   : keep window open
    new_window_cmd = f'cmd.exe /c start "" cmd.exe /k "{command}"'

    return _launch_new_window_command(new_window_cmd, cwd)


def _exec_cmd_new_window_macos(command: str, cwd: Optional[str]):
    """Launch a command in macOS Terminal.app and keep the shell open afterward."""
    # Terminal.app creates the shell itself, so setting cwd on the osascript process is not sufficient.
    # Explicitly cd to the requested working directory instead.
    terminal_command = command

    if cwd is not None:
        terminal_command = f'cd {shlex.quote(cwd)} && {terminal_command}'

    # Run command via bash, then keep Terminal open.
    bash_cmd = f"bash -lc {shlex.quote(terminal_command + '; exec bash')}"

    # Escape for AppleScript string literal.
    applescript_cmd = bash_cmd.replace('\\', '\\\\').replace('"', '\\"')

    applescript = (
        'tell application "Terminal"\n'
        '  activate\n'
        f'  do script "{applescript_cmd}"\n'
        'end tell'
    )

    debugUtils.log(debugUtils.Severity.DEBUG, tool_name, f'Launching in new window: {command}')

    try:
        subprocess.Popen(['osascript', '-e', applescript], stdin=None)
        return []
    except Exception as e:
        debugUtils.log(debugUtils.Severity.CRITICAL, tool_name, f'Failed to launch in new window: {e}')
        return False


def _exec_cmd_new_window_linux(command: str, cwd: Optional[str]):
    """Launch a command in an available Linux terminal and keep the terminal open afterward."""
    terminal = _pick_linux_terminal()

    if not terminal:
        msg = (
            'No supported terminal found '
            '(konsole/kgx/gnome-terminal/ptyxis/xterm/kitty/alacritty/wezterm/footclient...).'
        )
        debugUtils.log(debugUtils.Severity.CRITICAL, tool_name, msg)
        return False

    new_window_cmd = _build_linux_new_window_cmd(terminal, command)
    return _launch_new_window_command(new_window_cmd, cwd)


def _launch_new_window_command(command: str, cwd: Optional[str]):
    """Launch an already-built new-window shell command."""
    debugUtils.log(debugUtils.Severity.DEBUG, tool_name, f'Launching in new window: {command}')

    try:
        subprocess.Popen(command, shell=True, stdin=None, cwd=cwd)
        return []
    except Exception as e:
        debugUtils.log(debugUtils.Severity.CRITICAL, tool_name, f'Failed to launch in new window: {e}')
        return False


def _pick_linux_terminal() -> Optional[str]:
    """
    Find an available Linux terminal.

    - Respects $TERMINAL if set.
    - Detects KDE vs GNOME and prefers a likely default.
    - Includes common modern terminals that may exist on Fedora/Bazzite.
    """
    # Respect user preference if set.
    env_term = os.environ.get('TERMINAL')

    if env_term:
        # TERMINAL might include arguments; take the binary part.
        bin_name = env_term.split()[0]

        if shutil.which(bin_name):
            return bin_name

    # Desktop-session hints (KDE vs GNOME).
    desktop = (os.environ.get('XDG_CURRENT_DESKTOP') or '').lower()
    session = (os.environ.get('DESKTOP_SESSION') or '').lower()
    prefer_kde = 'kde' in desktop or 'plasma' in desktop or 'kde' in session or 'plasma' in session

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

    candidates = kde_first + gnome_first + common if prefer_kde else gnome_first + kde_first + common

    for terminal in candidates:
        if shutil.which(terminal):
            return terminal

    return None


def _build_linux_new_window_cmd(terminal: str, command: str) -> str:
    """
    Build a command that opens a new Linux terminal window and keeps it open after the command finishes.

    Uses bash -lc so the command behaves like a normal terminal command.
    """
    bash_lc_arg = shlex.quote(command)
    command_and_shell = shlex.quote(command + '; exec bash')

    match terminal:
        case 'konsole':
            return f'konsole --hold -e bash -lc {bash_lc_arg}'

        case 'gnome-terminal' | 'kgx':
            return f'{terminal} -- bash -lc {command_and_shell}'

        case 'ptyxis':
            return f'ptyxis -- bash -lc {command_and_shell}'

        case 'xterm':
            return f'xterm -hold -e bash -lc {bash_lc_arg}'

        case 'xfce4-terminal':
            return f'xfce4-terminal --hold -e bash -lc {command_and_shell}'

        case 'kitty':
            return f'kitty bash -lc {command_and_shell}'

        case 'alacritty':
            return f'alacritty -e bash -lc {command_and_shell}'

        case 'wezterm':
            return f'wezterm start -- bash -lc {command_and_shell}'

        case 'footclient':
            return f'footclient bash -lc {command_and_shell}'

        case _:
            # Generic fallback: many terminal emulators support "-e".
            return f'{terminal} -e bash -lc {command_and_shell}'