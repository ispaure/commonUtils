"""Verified ZIP/TAR creation without deleting or replacing input files."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import tarfile
import zipfile

from ..operations import check_cancelled
from ..streams import stream_signature
from ..zip_access import create_archive, directory_entries
from .reading import reader


def create(sources, destination, *, format='zip', password=None, level=6,
           progress=lambda *args: None, cancelled=lambda: False):
    if format == 'zip':
        return create_archive(sources, destination, password=password,
                              compression=zipfile.ZIP_STORED if level == 0 else zipfile.ZIP_DEFLATED,
                              compresslevel=None if level == 0 else level, progress=progress, cancelled=cancelled)
    if password:
        raise ValueError('Encryption is available for ZIP only')
    modes = {'tar': 'w', 'tar.gz': 'w:gz', 'tar.xz': 'w:xz'}
    mode = modes[format]
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f'Output already exists: {destination}')
    sources = tuple(dict.fromkeys(Path(source).absolute() for source in sources))
    if not sources:
        raise ValueError('Select at least one source')
    plan = []
    for source in sources:
        if source.is_symlink() or not source.exists():
            raise ValueError(f'Source must exist and cannot be a symbolic link: {source}')
        if source == destination or (source.is_dir() and destination.resolve().is_relative_to(source.resolve())):
            raise ValueError('The output archive must be outside the selected sources')
        if any(other != source and other.is_dir() and source.is_relative_to(other) for other in sources):
            continue
        plan.extend(directory_entries(source, cancelled=cancelled) if source.is_dir() else [(source, source.name)])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.logistics-archive-', dir=destination.parent) as temp:
        staged = Path(temp) / 'archive'
        expected = {}
        signatures = {source: source.stat() for source, name in plan}
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        total = sum(source.stat().st_size for source, name in plan if source.is_file())
        done = 0
        with tarfile.open(staged, mode) as archive:
            for source, name in plan:
                check_cancelled(cancelled)
                if source.is_symlink() or identity(source.stat()) != identity(signatures[source]):
                    raise ValueError(f'Source changed while archiving: {source}')
                info = archive.gettarinfo(str(source), arcname=name)
                if not (info.isfile() or info.isdir()):
                    raise ValueError(f'Cannot archive a nonregular file: {source}')
                if info.isfile():
                    # Hash and add from the same descriptor, then verify staged bytes.
                    with source.open('rb') as stream:
                        expected[name] = stream_signature(stream, cancelled=cancelled)
                        stream.seek(0)
                        class CancellableStream:
                            def read(self, size):
                                nonlocal done
                                check_cancelled(cancelled)
                                data = stream.read(size)
                                done += len(data)
                                progress(done, total, f'Creating {name}')
                                return data
                        archive.addfile(info, CancellableStream())
                else:
                    archive.addfile(info)
        with reader(staged) as (archive, _):
            for item in archive.getmembers():
                if item.isfile():
                    with archive.extractfile(item) as stream:
                        if stream_signature(stream, cancelled=cancelled) != expected[item.name]:
                            raise ValueError('Archive verification failed')
        for source, before in signatures.items():
            if source.is_symlink() or identity(source.stat()) != identity(before):
                raise ValueError(f'Source changed while archiving: {source}')
        with staged.open('r+b') as stream:
            os.fsync(stream.fileno())
        check_cancelled(cancelled)
        os.link(staged, destination)
    return destination
