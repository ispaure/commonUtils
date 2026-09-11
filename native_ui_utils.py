"""
Native UI utilities that do not depend on PySide or another GUI framework.

This module provides lightweight, platform-specific UI functionality using facilities available on the operating system,
such as native Windows APIs, AppleScript on macOS, and common dialog tools on Linux.

It primarily serves as the non-PySide backend for ``uiUtils`` when a Qt application context is unavailable or undesirable.
For Qt/PySide-based UI functionality, use ``pySideUtils`` instead.
"""

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

from .debugUtils import *
import ctypes
from .osUtils import *
import subprocess
import shutil

# Blue Hole
from .wrappers import cmdShellWrapper


# ----------------------------------------------------------------------------------------------------------------------
# CONSTANTS

_WINDOWS_MB_OK = 0x00000000
_WINDOWS_MB_OKCANCEL = 0x00000001
_WINDOWS_MB_SETFOREGROUND = 0x00010000
_WINDOWS_MB_TOPMOST = 0x00040000
_WINDOWS_MB_TASKMODAL = 0x00002000
_WINDOWS_IDOK = 1


# ----------------------------------------------------------------------------------------------------------------------
# HELPERS

def _normalize_message(message: str) -> str:
    """Convert escaped newlines and tabs into their actual characters."""
    return message.replace('\\n', '\n').replace('\\t', '\t')


def _sanitize_linux_dialog_text(value: str) -> str:
    """Remove quote characters that may interfere with Linux dialog utilities."""
    return value.replace('"', '').replace("'", "")


def _run_dialog_command(args: list[str]) -> int:
    """Execute a dialog command and return its process return code."""
    try:
        process = subprocess.run(args, capture_output=True, text=True)
        return process.returncode
    except Exception:
        return 1


def _get_windows_owner_hwnd() -> int:
    """
    Try to get a sensible owner window handle for native Windows message boxes.

    Prefer the foreground window, then the active window, then fall back to 0.
    """
    try:
        user32 = ctypes.windll.user32

        hwnd = user32.GetForegroundWindow()
        if hwnd:
            return hwnd

        hwnd = user32.GetActiveWindow()
        if hwnd:
            return hwnd

    except Exception as ex:
        log(Severity.WARNING, 'UI Utils', f'Could not get Windows owner hwnd: {ex}')

    return 0


def _display_msg_box_ok_windows(title: str, message: str) -> bool:
    """Display a message box with an OK button using the native Windows API."""
    hwnd = _get_windows_owner_hwnd()
    flags = _WINDOWS_MB_OK | _WINDOWS_MB_SETFOREGROUND | _WINDOWS_MB_TOPMOST | _WINDOWS_MB_TASKMODAL

    ctypes.windll.user32.MessageBoxW(hwnd, message, title, flags)
    return True


def _display_msg_box_ok_macos(title: str, message: str) -> bool:
    """Display a message box with an OK button using AppleScript."""
    applescript = r'''
on run argv
    set theTitle to item 1 of argv
    set theMessage to item 2 of argv
    tell application "System Events"
        activate
        display dialog theMessage with title theTitle buttons {"OK"} default button "OK"
    end tell
end run
'''.strip()

    process = subprocess.run(["osascript", "-e", applescript, title, message], capture_output=True, text=True)

    if process.returncode != 0:
        print("osascript failed:", process.returncode)
        if process.stderr:
            print("osascript stderr:", process.stderr.strip())

    return True


def _display_msg_box_ok_linux(title: str, message: str) -> bool:
    """
    Display a message box with an OK button using an available Linux dialog utility.

    Tries kdialog, zenity, and xmessage in that order before falling back to a console prompt.
    """
    safe_title = _sanitize_linux_dialog_text(title)
    safe_message = _sanitize_linux_dialog_text(message)

    if shutil.which("kdialog"):
        result = _run_dialog_command(["kdialog", "--title", safe_title, "--msgbox", safe_message])

        if result != 0:
            print("kdialog return code:", result)

        return True

    if shutil.which("zenity"):
        _run_dialog_command(["zenity", "--info", "--title", safe_title, "--text", safe_message, "--ok-label=OK"])
        return True

    if shutil.which("xmessage"):
        _run_dialog_command(["xmessage", "-center", "-title", safe_title, "-buttons", "OK:0", safe_message])
        return True

    try:
        input(f"{safe_title}\n{safe_message}\nPress Enter to continue...")
        return True
    except Exception:
        pass

    log(Severity.CRITICAL, 'uiUtils: Could not popup message', f"{safe_title}\n{safe_message}")
    return False


def _display_msg_box_ok_cancel_windows(title: str, message: str) -> bool:
    """
    Display an OK/Cancel message box using the native Windows API.

    Returns True when OK is selected.
    Returns False when Cancel is selected or the dialog is dismissed.
    """
    hwnd = _get_windows_owner_hwnd()
    flags = _WINDOWS_MB_OKCANCEL | _WINDOWS_MB_SETFOREGROUND | _WINDOWS_MB_TOPMOST | _WINDOWS_MB_TASKMODAL
    result = ctypes.windll.user32.MessageBoxW(hwnd, message, title, flags)

    return result == _WINDOWS_IDOK


def _display_msg_box_ok_cancel_macos(title: str, message: str) -> bool:
    """
    Display an OK/Cancel message box using AppleScript.

    This preserves the existing cmdShellWrapper-based implementation.
    """
    message = message.replace('"', '').replace("'", '')

    command_str = (
        "osascript -e 'Tell application \"System Events\" to display dialog "
        "\"{message}\" with title \"{title}\"'"
    ).format(message=message, title=title)

    return_val = cmdShellWrapper.exec_cmd(command_str)
    return 'OK' in return_val[0]


def _display_msg_box_ok_cancel_linux(title: str, message: str) -> bool:
    """
    Display an OK/Cancel message box using an available Linux dialog utility.

    Tries kdialog, zenity, and xmessage in that order before falling back to a console prompt.
    """
    safe_title = _sanitize_linux_dialog_text(title)
    safe_message = _sanitize_linux_dialog_text(message)

    if shutil.which("kdialog"):
        result = _run_dialog_command(["kdialog", "--title", safe_title, "--yesno", safe_message])
        return result == 0

    if shutil.which("zenity"):
        result = _run_dialog_command([
            "zenity", "--question", "--title", safe_title, "--text", safe_message, "--ok-label=OK",
            "--cancel-label=Cancel"
        ])
        return result == 0

    if shutil.which("xmessage"):
        result = _run_dialog_command(
            ["xmessage", "-center", "-title", safe_title, "-buttons", "OK:0,Cancel:1", safe_message]
        )
        return result == 0

    try:
        response = input(
            f"{safe_title}\n{safe_message}\nType 'ok' to continue, anything else to cancel: "
        ).strip().lower()

        return response in ("ok", "o", "yes", "y")

    except Exception:
        return False


# ----------------------------------------------------------------------------------------------------------------------
# CODE

def display_msg_box_ok(title: str, message: str) -> bool:
    """
    Display a native message box with an OK button.

    Returns True once the dialog has been handled.

    :param title: Dialog box title
    :type title: str
    :param message: Message to be shown in dialog box
    :type message: str
    :return: Whether the dialog was handled.
    :rtype: bool
    """
    message = _normalize_message(message)

    match get_os():
        case OS.WIN:
            return _display_msg_box_ok_windows(title, message)
        case OS.MAC:
            return _display_msg_box_ok_macos(title, message)
        case OS.LINUX:
            return _display_msg_box_ok_linux(title, message)

    return False


def display_msg_box_ok_cancel(title: str, message: str) -> bool:
    """
    Display a native OK/Cancel dialog.

    Returns True only when the user selects OK.
    Returns False when the user selects Cancel or otherwise dismisses the dialog.

    :param title: Dialog box title
    :type title: str
    :param message: Message to be shown in dialog box
    :type message: str
    :return: Whether the user selected OK.
    :rtype: bool
    """
    print('Showing dialog box.')

    message = _normalize_message(message)

    match get_os():
        case OS.WIN:
            return _display_msg_box_ok_cancel_windows(title, message)
        case OS.MAC:
            return _display_msg_box_ok_cancel_macos(title, message)
        case OS.LINUX:
            return _display_msg_box_ok_cancel_linux(title, message)

    return False
