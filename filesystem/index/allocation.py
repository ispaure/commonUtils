"""File allocation metadata without reading file contents.

Unknown allocation is -1, never substituted with logical size. Totals count
file allocations by path; links and filesystem metadata are excluded.
"""
import os
from functools import lru_cache


def allocated_size(path, info):
    blocks = getattr(info, 'st_blocks', None)
    if blocks is not None:
        return max(0, blocks * 512)
    if os.name == 'nt':
        return _windows_allocation(path, info)
    return -1


@lru_cache(maxsize=1)
def _windows_api():
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                    ctypes.c_void_p, wintypes.DWORD]
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetCompressedFileSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetCompressedFileSizeW.restype = wintypes.DWORD
    return kernel


def _windows_allocation(path, info):
    import ctypes
    from ctypes import wintypes
    kernel = _windows_api()
    text = os.path.abspath(path)
    if not text.startswith('\\\\?\\'):
        text = '\\\\?\\UNC\\' + text[2:] if text.startswith('\\\\') else '\\\\?\\' + text
    # Compressed/sparse storage is smaller than its reserved allocation size.
    if getattr(info, 'st_file_attributes', 0) & (0x800 | 0x200):
        high = wintypes.DWORD()
        ctypes.set_last_error(0)
        low = kernel.GetCompressedFileSizeW(text, ctypes.byref(high))
        return -1 if low == 0xffffffff and ctypes.get_last_error() else (high.value << 32) | low

    class StandardInfo(ctypes.Structure):
        _fields_ = [('allocation', ctypes.c_longlong), ('end', ctypes.c_longlong),
                    ('links', wintypes.DWORD), ('delete_pending', ctypes.c_ubyte),
                    ('directory', ctypes.c_ubyte)]

    # Read attributes only, share with writers/deleters, and avoid opening
    # reparse-point contents (including download-on-demand placeholders).
    handle = kernel.CreateFileW(text, 0x80, 7, None, 3, 0x200000, None)
    if handle == ctypes.c_void_p(-1).value:
        return -1
    try:
        value = StandardInfo()
        if not kernel.GetFileInformationByHandleEx(handle, 1, ctypes.byref(value), ctypes.sizeof(value)):
            return -1
        return max(0, value.allocation)
    finally:
        kernel.CloseHandle(handle)
