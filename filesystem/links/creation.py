"""Exclusive link creation: no replacement, deletion, GUI or automatic elevation."""
import base64
import os
from pathlib import Path
import subprocess


def create_link(source, destination, kind='symbolic'):
    source = Path(source).resolve(strict=True)
    destination = Path(destination).absolute()
    if not source.is_file() and not source.is_dir():
        raise ValueError('Pick a regular file or folder as the link source')
    if os.path.lexists(destination):
        raise FileExistsError(f'Destination already exists: {destination}')
    if not destination.parent.is_dir():
        raise NotADirectoryError(str(destination.parent))
    if kind == 'symbolic':
        try:
            destination.symlink_to(source, target_is_directory=source.is_dir())
        except OSError as error:
            if os.name == 'nt' and getattr(error, 'winerror', None) == 1314:
                raise PermissionError('Windows requires Developer Mode or symbolic-link privileges to create this link.') from error
            raise
    elif kind == 'hard':
        if not source.is_file():
            raise ValueError('Hard links work with files, not folders')
        if source.stat().st_dev != destination.parent.stat().st_dev:
            raise ValueError('Hard links must stay on the same filesystem/volume')
        os.link(source, destination)
    elif kind == 'junction':
        if os.name != 'nt' or not source.is_dir():
            raise ValueError('Junctions work with local Windows folders')
        import ctypes
        # Reject UNC and mapped network volumes; junction targets are local.
        for path in (source, destination.parent.resolve()):
            if path.anchor.startswith('\\\\') or ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) == 4:
                raise ValueError('Use a symbolic link for network folders')
        literal = lambda path: "'" + str(path).replace("'", "''") + "'"
        script = "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path " + literal(destination) + ' -Target ' + literal(source) + ' | Out-Null'
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                                capture_output=True, timeout=30)
        if result.returncode:
            raise OSError(result.stderr.decode(errors='replace').strip() or 'Could not create junction')
    else:
        raise ValueError('Unknown link type')
    return destination


def create_link_in_directory(source, directory, kind='symbolic'):
    """Keep the original name when free, otherwise allocate ' - Link (N)' names."""
    source, directory = Path(source), Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(str(directory))
    stem, suffix = (source.stem, source.suffix) if source.is_file() else (source.name, '')
    for attempt in range(10000):
        name = source.name if attempt == 0 else stem + ' - Link' + (f' ({attempt})' if attempt > 1 else '') + suffix
        try:
            return create_link(source, directory / name, kind)
        except FileExistsError:
            continue
    raise FileExistsError('Could not find an unused link name')
