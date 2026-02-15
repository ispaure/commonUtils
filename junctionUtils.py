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

import os
import ctypes
from ctypes import wintypes
from pathlib import Path

# Define constants
FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003  # Junction tag
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000


# Structs and Windows API setup
class REPARSE_DATA_BUFFER(ctypes.Structure):
    _fields_ = [
        ("ReparseTag", wintypes.DWORD),
        ("ReparseDataLength", wintypes.WORD),
        ("Reserved", wintypes.WORD),
        ("DataBuffer", wintypes.BYTE * 1)
    ]


def is_junction(path):
    if isinstance(path, str):
        path_str = path
    elif isinstance(path, Path):
        path_str = str(path)
    else:
        print('Wrong type!')
        return None

    if not os.path.exists(path_str):
        return False

    # Open the file handle with BACKUP_SEMANTICS for directories
    handle = ctypes.windll.kernel32.CreateFileW(
        wintypes.LPWSTR(path_str),
        0,  # No access needed, just query
        0,  # No sharing
        None,
        3,  # OPEN_EXISTING
        FILE_FLAG_BACKUP_SEMANTICS | FILE_ATTRIBUTE_REPARSE_POINT,
        None
    )
    if handle == -1:
        raise OSError(f"Failed to open handle for {path_str}")

    try:
        # Query the reparse point
        buffer = REPARSE_DATA_BUFFER()
        bytes_returned = wintypes.DWORD()
        result = ctypes.windll.kernel32.DeviceIoControl(
            handle,
            0x900A8,  # FSCTL_GET_REPARSE_POINT
            None,
            0,
            ctypes.byref(buffer),
            ctypes.sizeof(buffer),
            ctypes.byref(bytes_returned),
            None
        )

        if not result:
            return False

        # Check the reparse tag
        return buffer.ReparseTag == IO_REPARSE_TAG_MOUNT_POINT
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)