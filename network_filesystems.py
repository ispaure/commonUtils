"""Network mount policy using local mount metadata, without probing share contents."""
from pathlib import Path, PureWindowsPath
import ctypes
import re
import subprocess
import sys
from time import monotonic

_NETWORK_TYPES = {'nfs', 'nfs4', 'smbfs', 'cifs', 'afpfs', 'afp', 'sshfs', 'fuse.sshfs',
                  'davfs', 'davfs2', 'webdav', 'fuse.rclone', '9p', 'ceph', 'glusterfs',
                  'fuse.smbnetfs', 'fuse.curlftpfs', 'fuse.gvfsd-fuse'}
_mounts = ()
_mounts_checked = -10.


def _drive_type(root):
    function = ctypes.windll.kernel32.GetDriveTypeW
    function.argtypes = [ctypes.c_wchar_p]
    function.restype = ctypes.c_uint
    return function(str(root))


def _unescape_mount(path):
    return re.sub(r'\\([0-7]{3})', lambda match: chr(int(match.group(1), 8)), path)


def _mounted_network_roots():
    if sys.platform == 'win32':
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        return tuple(Path(f'{chr(65 + i)}:/') for i in range(26)
                     if mask & (1 << i) and _drive_type(f'{chr(65 + i)}:/') == 4)
    if sys.platform.startswith('linux'):
        roots = []
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            mount, details = line.split(' - ', 1)
            if details.split()[0].lower() in _NETWORK_TYPES:
                roots.append(Path(_unescape_mount(mount.split()[4])))
        return tuple(roots)
    if sys.platform == 'darwin':
        result = subprocess.run(['/sbin/mount'], capture_output=True, text=True, timeout=2, check=True)
        return tuple(Path(match.group(1)) for line in result.stdout.splitlines()
                     if (match := re.match(r'.+ on (.+) \(([^,)]+)', line))
                     and match.group(2).lower() in _NETWORK_TYPES)
    return ()


def network_mount_roots(*, refresh=False):
    global _mounts, _mounts_checked
    if refresh or monotonic() - _mounts_checked > 2:
        try:
            _mounts = _mounted_network_roots()
        except (OSError, ValueError, subprocess.SubprocessError):
            pass  # Keep the last mount table if a transient metadata query fails.
        _mounts_checked = monotonic()
    return _mounts


def is_network_location(path, *, refresh=False):
    value = str(path)
    if value.startswith(('\\\\', '//')):
        return True
    if sys.platform == 'win32':
        root = PureWindowsPath(value).anchor
        return bool(root) and _drive_type(root) == 4
    roots = network_mount_roots(refresh=refresh)
    path = Path(path).absolute()
    if any(path == root or root in path.parents for root in roots):
        return True
    path = path.resolve()
    return any(path == root or root in path.parents for root in roots)
