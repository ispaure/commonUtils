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
import platform
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


class Arch(Enum):
    X86_64 = "x86_64"
    X86_32 = "x86"
    ARM_64 = "aarch64"
    ARM_32 = "arm"
    UNKNOWN = "unknown"

def get_arch() -> Arch:
    m = platform.machine().lower()

    # Normalize common values
    if m in ("x86_64", "amd64"):
        return Arch.X86_64
    if m in ("i386", "i686", "x86"):
        return Arch.X86_32
    if m in ("aarch64", "arm64"):
        return Arch.ARM_64
    if m.startswith("arm") or m in ("armv7l", "armv6l"):
        return Arch.ARM_32

    return Arch.UNKNOWN


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
