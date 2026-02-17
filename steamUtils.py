import os
from typing import *
from .osUtils import *


def is_linux_steam_big_picture() -> bool:
    """ Return if the application was launched in Linux Steam Big Picture Mode """

    match get_os():
        case OS.LINUX:
            # Most reliable indicator
            if os.environ.get("STEAM_BIGPICTURE") == "1":
                return True
            # Also commonly present in Steam Big Picture / Deck sessions
            if os.environ.get("SteamTenfoot") == "1":
                return True
            # Steam Deck / gamescope sessions
            if os.environ.get("XDG_CURRENT_DESKTOP") == "gamescope":
                return True
            return False

        case _:
            return False
