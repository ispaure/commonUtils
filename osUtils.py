import sys
from enum import Enum


class OS(Enum):
    WINDOWS = "Windows"
    MACOS = "macOS"
    LINUX = "Linux"


def get_os() -> str:
    match sys.platform:
        case 'win32':
            return 'Windows'
        case 'darwin':
            return 'macOS'
        case 'linux':
            return 'Linux'
        case _:
            return 'Unknown'


def get_os_path(path_win=None, path_mac=None, path_linux=None):
    """Returns the correct path based on the current operating system."""
    match get_os():
        case 'Windows':
            return path_win
        case 'macOS':
            return path_mac
        case 'Linux':
            return path_linux
        case _:
            return None  # If OS is unknown or no path is provided
