"""
Basic UI Functions that do not rely on PySide
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
# CODE


def display_msg_box_ok(title: str, message: str):
    """
    Displays a simple message box with an OK button.
    Pauses script until user presses OK.
    :param title: Dialog box title
    :type title: str
    :param message: Message to be shown in dialog box
    :type message: str
    """
    import sys
    import ctypes

    # Prevent escape sequences
    message = message.replace('\\n', '\n').replace('\\t', '\t')

    match get_os():
        case OS.WIN:
            class MbConstants:
                MB_OK = 0
            ctypes.windll.user32.MessageBoxW(0, message, title, MbConstants.MB_OK)

        case OS.MAC:  # macOS
            message = message.replace('"', '').replace("'", '')
            import subprocess
            cmd = f"""osascript -e 'Tell application "System Events" to display dialog "{message}" with title "{title}" buttons {{"OK"}} default button "OK"'"""
            subprocess.run(cmd, shell=True)

        case OS.LINUX:
            # Mirror show_prompt Linux approach: try GUI tools, then a blocking console fallback.
            safe_title = title.replace('"', '').replace("'", "")
            safe_message = message.replace('"', '').replace("'", "")

            def run_cmd(args: list[str]) -> int:
                # Return process returncode; never raises on non-zero.
                try:
                    p = subprocess.run(args, capture_output=True, text=True)
                    return p.returncode
                except Exception:
                    return 1

            # 1) KDE: kdialog (blocks until OK)
            if shutil.which("kdialog"):
                print("method 1")

                # IMPORTANT: don't rely on outer imports; make it local & explicit
                import subprocess

                def run_cmd(args: list[str]) -> int:
                    # Return process returncode; never raises on non-zero.
                    try:
                        p = subprocess.run(args, capture_output=True, text=True)
                        # Debug if it fails (this is what your old code hid)
                        if p.returncode != 0:
                            print("kdialog return code:", p.returncode)
                            if (p.stdout or "").strip():
                                print("kdialog stdout:", p.stdout.strip())
                            if (p.stderr or "").strip():
                                print("kdialog stderr:", p.stderr.strip())
                        return p.returncode
                    except Exception as e:
                        print("kdialog exception:", repr(e))
                        return 1

                rc = run_cmd(["kdialog", "--title", safe_title, "--msgbox", safe_message])
                # Regardless of rc, we attempted to show the message; return to avoid falling through.
                return

            # 2) GNOME: zenity (blocks until OK)
            if shutil.which("zenity"):
                print('method 2')
                run_cmd([
                    "zenity",
                    "--info",
                    "--title", safe_title,
                    "--text", safe_message,
                    "--ok-label=OK",
                ])
                return

            # 3) X11: xmessage (blocks until OK)
            if shutil.which("xmessage"):
                print('method3')
                run_cmd([
                    "xmessage",
                    "-center",
                    "-title", safe_title,
                    "-buttons", "OK:0",
                    safe_message,
                ])
                return

            # 4) Last resort: blocking console prompt (best-effort)
            try:
                input(f"{safe_title}\n{safe_message}\nPress Enter to continue...")
                return
            except Exception:
                pass

            # Absolute last resort: log (non-blocking)
            log(Severity.CRITICAL, 'uiUtils: Could not popup message', f"{safe_title}\n{safe_message}")
    return True


def display_msg_box_ok_cancel(title, message):
    """
    Displays dialog box
    :param title: Dialog box title
    :type title: str
    :param message: Message to be shown in dialog box
    :type message: str
    """
    print('Showing dialog box.')

    class MbConstants:
        MB_OKCANCEL = 1
        IDCANCEL = 2
        IDOK = 1

    # Prevent escape sequences
    message = message.replace('\\n', '\n').replace('\\t', '\t')

    # Show Dialog Window (Windows) and return user input
    def show_prompt_windows(message, title):
        return ctypes.windll.user32.MessageBoxW(0, message, title, MbConstants.MB_OKCANCEL)

    # Show Dialog Window (MacOS) and return user input
    def show_prompt_macos(message, title):
        command_str = "osascript -e 'Tell application \"System Events\" to display dialog \"{message}\" with title \"{title}\"'".format(message=message, title=title)
        return_val = cmdShellWrapper.exec_cmd(command_str)
        return return_val

    # Since Blender API doesn't have proper message box that waits on user, we have to get a bit creative.

    match get_os():  # Solution which only works on Windows
        case OS.WIN:
            rc = show_prompt_windows(message, title)
            if rc == MbConstants.IDOK:
                return True
            elif rc == MbConstants.IDCANCEL:
                return False

        case OS.MAC:
            message = message.replace('"', '')
            message = message.replace("'", '')
            if 'OK' in show_prompt_macos(message, title)[0]:
                return True
            else:
                return False

        case OS.LINUX:
            # Minimal sanitization for shell tools
            safe_title = title.replace('"', '').replace("'", "")
            safe_message = message.replace('"', '').replace("'", "")

            def run_cmd(args: list[str]) -> int:
                # Return process returncode; never raises on non-zero.
                try:
                    p = subprocess.run(args, capture_output=True, text=True)
                    return p.returncode
                except Exception:
                    return 1

                # 1) KDE: kdialog (0=yes/ok, 1=no/cancel)

            if shutil.which("kdialog"):
                # --yesno shows Yes/No; good enough for OK/Cancel semantics
                rc = run_cmd(["kdialog", "--title", safe_title, "--yesno", safe_message])
                if rc == 0:
                    return True
                return False

                # 2) GNOME: zenity (0=OK, 1=Cancel)
            if shutil.which("zenity"):
                rc = run_cmd([
                    "zenity",
                    "--question",
                    "--title", safe_title,
                    "--text", safe_message,
                    "--ok-label=OK",
                    "--cancel-label=Cancel",
                ])
                if rc == 0:
                    return True
                return False

                # 3) X11: xmessage (button return codes vary by version; use explicit mapping)
            if shutil.which("xmessage"):
                # xmessage returns the "exit code" of the chosen button when mapped as OK:0,Cancel:1
                rc = run_cmd([
                    "xmessage",
                    "-center",
                    "-title", safe_title,
                    "-buttons", "OK:0,Cancel:1",
                    safe_message,
                ])
                if rc == 0:
                    return True
                return False

                # 4) Last resort: console prompt (won't block Blender UI if launched from terminal)
            try:
                resp = input(f"{safe_title}\n{safe_message}\nType 'ok' to continue, anything else to cancel: ").strip().lower()
                if resp in ("ok", "o", "yes", "y"):
                    return True
            except Exception:
                pass

            return False
