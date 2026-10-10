"""Verified atomic ZIP rebuilding with explicit additions and removals."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os

from ..operations import check_cancelled
from ..streams import copy_stream
from ..zip_access import (authenticate, copy_member_info, _name_key, open_archive,
                         archive_manifest, create_archive)


def update_zip(path, *, sources=(), remove=(), password=None,
               progress=lambda *args: None, cancelled=lambda: False):
    """Rebuild a ZIP, verify decrypted hashes, then replace it atomically.

    Additions cannot silently replace an entry. Removing a directory removes its
    descendants. Mixed encrypted/plain ZIPs are rejected rather than changing
    their protection policy. A changed source archive aborts publication.
    """
    path = Path(path).absolute()
    if path.is_symlink():
        raise ValueError('Cannot edit an archive through a symbolic link')
    before = path.stat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    authenticate(path, password, all_members=True, for_rewrite=True, cancelled=cancelled)
    original = archive_manifest(path, password=password, progress=progress, cancelled=cancelled)
    retained = {name: digest for name, digest in original.items()
                if not any(name.replace('\\', '/').rstrip('/') == target.rstrip('/')
                           or name.replace('\\', '/').startswith(target.rstrip('/') + '/') for target in remove)}
    with TemporaryDirectory(prefix='.logistics-edit-', dir=path.parent) as temp:
        extra = Path(temp) / 'additions.zip'
        if sources:
            create_archive(sources, extra, progress=progress, cancelled=cancelled)
            additions = archive_manifest(extra, cancelled=cancelled)
        else:
            additions = {}
        names = {_name_key(name) for name in retained}
        if any(_name_key(name) in names for name in additions):
            raise ValueError('An added entry already exists. Remove it first or choose a different source name.')
        expected = retained | additions
        staged = Path(temp) / 'result.zip'
        with open_archive(staged, 'w', password=password) as output:
            for source_path, secret, included in ((path, password, retained), (extra, None, additions)):
                if not included:
                    continue
                with open_archive(source_path, password=secret) as incoming:
                    if source_path == path:
                        output.comment = incoming.comment
                    for item in incoming.infolist():
                        if item.filename not in included:
                            continue
                        check_cancelled(cancelled)
                        progress(0, 0, f'Rebuilding {item.filename}')
                        info = copy_member_info(item, output)
                        if item.is_dir():
                            output.writestr(info, b'')
                        else:
                            with incoming.open(item) as source, output.open(info, 'w', force_zip64=True) as target:
                                copy_stream(source, target, cancelled=cancelled)
        if archive_manifest(staged, password=password, progress=progress, cancelled=cancelled) != expected:
            raise ValueError('Archive verification failed; original archive was kept')
        if path.is_symlink() or identity(path.stat()) != identity(before):
            raise ValueError('The archive changed during editing; original archive was kept')
        with staged.open('r+b') as stream:
            os.fsync(stream.fileno())
        os.chmod(staged, before.st_mode & 0o777)
        check_cancelled(cancelled)
        os.replace(staged, path)
    return path
