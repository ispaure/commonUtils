"""Transactional extraction of whole archives or selected subtrees."""
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import shutil

from ..operations import check_cancelled
from ..streams import copy_stream
from .reading import reader, _members, _name, _directory, _stream


def extract(path, destination, *, selected=None, password=None,
            progress=lambda *args: None, cancelled=lambda: False):
    """Extract into a NEW folder; never overwrite existing user files.

    Validate every member, stage the complete selection, then reserve the output
    with exclusive mkdir. Cancellation or bad passwords leave no partial output.
    """
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Choose a new destination folder; existing folders are never overwritten.')
    selection = tuple(selected) if selected is not None else None
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.logistics-extract-', dir=destination.parent) as temp:
        stage = Path(temp) / 'contents'
        stage.mkdir()
        with reader(path, password) as (archive, is_zip):
            members = [item for item in _members(archive, is_zip)
                       if selection is None or any(_name(item, is_zip).rstrip('/') == name.rstrip('/')
                           or _name(item, is_zip).startswith(name.rstrip('/') + '/') for name in selection)]
            if not members and selection:
                raise ValueError('No selected entries found')
            total = sum(item.file_size if is_zip else item.size for item in members)
            done = 0
            for item in members:
                check_cancelled(cancelled)
                name = _name(item, is_zip)
                target = stage / name
                if not target.resolve().is_relative_to(stage.resolve()):
                    raise ValueError(f'Unsafe archive member: {name}')
                if _directory(item, is_zip):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    def advanced(size):
                        nonlocal done
                        done += size
                        progress(done, total, f'Extracting {name}')
                    with _stream(archive, item, is_zip) as source, target.open('xb') as output:
                        copy_stream(source, output, cancelled=cancelled, progress=advanced)
                    # Retain executable bits for Unix scripts, without restoring
                    # ownership, setuid bits or restrictive archive permissions.
                    mode = (item.external_attr >> 16) if is_zip and item.create_system == 3 else (item.mode if not is_zip else 0)
                    os.chmod(target, (target.stat().st_mode & 0o777) | (mode & 0o111))
                    try:
                        stamp = datetime(*item.date_time).timestamp() if is_zip else item.mtime
                        os.utime(target, (stamp, stamp))
                    except (ValueError, OSError, OverflowError):
                        pass
        check_cancelled(cancelled)
        destination.mkdir()  # exclusive reservation, even against concurrent creation
        try:
            for child in stage.iterdir():
                os.replace(child, destination / child.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return destination
