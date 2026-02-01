import sys
from enum import Enum


class OS(Enum):
    WIN = "Windows"
    MAC = "macOS"
    LINUX = "Linux"
    UNKNOWN = "Unknown"


def get_os() -> OS:
    match sys.platform:
        case 'win32':
            return OS.WIN
        case 'darwin':
            return OS.MAC
        case 'linux':
            return OS.LINUX
        case _:
            return OS.UNKNOWN


def get_os_path(path_win=None, path_mac=None, path_linux=None):
    """Returns the correct path based on the current operating system."""
    match get_os():
        case OS.WIN:
            return path_win
        case OS.MAC:
            return path_mac
        case OS.LINUX:
            return path_linux
        case _:
            raise RuntimeError(f'Unsupported platform: {sys.platform}')
