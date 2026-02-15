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
            raise RuntimeError(f'Unsupported platform: {sys.platform}')


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
