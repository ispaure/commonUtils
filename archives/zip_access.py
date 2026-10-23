"""Shared ZIP access with AES-256 writes and validated, streaming extraction.

No configuration lookup, prompts or password persistence belongs in this module.
Passwords are UTF-8 strings or bytes. Reading also accepts legacy ZipCrypto;
writing a password always selects WinZip AES-256. Filenames remain visible.
"""

from contextlib import contextmanager
import os
from pathlib import Path, PurePosixPath
import stat
from tempfile import NamedTemporaryFile
import zipfile
import zlib

from .members import copy_member_info, name_key
from ..runtime.operations import check_cancelled
from ..runtime.streams import CHUNK_SIZE, copy_stream, iter_chunks, stream_signature


class ArchivePasswordError(RuntimeError):
    """Authentication failed; messages deliberately never contain the password."""


def password_bytes(password):
    if password is None:
        return None
    if isinstance(password, str):
        return password.encode('utf-8')
    if isinstance(password, bytes):
        return password
    raise TypeError('ZIP password must be text or bytes')


def is_encrypted(path):
    with zipfile.ZipFile(path) as archive:
        return any(member.flag_bits & 1 for member in archive.infolist())


@contextmanager
def open_archive(path, mode='r', *, password=None, compression=zipfile.ZIP_DEFLATED, compresslevel=None):
    """Open plain/ZipCrypto/AES ZIPs; never silently write unencrypted output."""
    password = password_bytes(password)
    label = Path(path).name if isinstance(path, (str, os.PathLike)) else str(getattr(path, 'name', 'archive'))
    source = str(path) if isinstance(path, os.PathLike) else path
    if mode not in ('r', 'w', 'x'):
        raise ValueError('Only ZIP read, write and exclusive-create modes are supported')
    encrypted = is_encrypted(path) if mode == 'r' else password is not None
    if mode != 'r' and encrypted and not password:
        raise ValueError('An encrypted ZIP requires a nonempty password')
    if mode == 'r' and encrypted and not password:
        raise ArchivePasswordError(f'Archive password required: {label}')
    bad_zip_errors = (zipfile.BadZipFile,)
    if encrypted:
        try:
            import pyzipper
        except ImportError as error:
            raise RuntimeError('Encrypted ZIP access requires the optional pyzipper dependency') from error
        bad_zip_errors += (pyzipper.BadZipFile,)
        archive = pyzipper.AESZipFile(source, mode, compression=compression, compresslevel=compresslevel)
        archive.setpassword(password)
        if mode != 'r':
            archive.setencryption(pyzipper.WZ_AES, nbits=256)
    else:
        archive = zipfile.ZipFile(path, mode, compression=compression, compresslevel=compresslevel)
    try:
        with archive:
            yield archive
    except RuntimeError as error:
        if 'password' in str(error).lower():
            raise ArchivePasswordError(f'Archive password incorrect: {label}') from None
        raise
    except bad_zip_errors as error:
        if encrypted and ('hmac' in str(error).lower() or 'bad crc' in str(error).lower()):
            raise ArchivePasswordError(
                f'Archive password incorrect or encrypted data damaged: {label}') from None
        raise zipfile.BadZipFile(str(error)) from None
    except zlib.error:
        if encrypted:
            raise ArchivePasswordError(
                f'Archive password incorrect or encrypted data damaged: {label}') from None
        raise


def validate_members(archive):
    """Validate all names before extraction, for encrypted and plain ZIPs alike."""
    seen = set()
    kinds = {}
    for member in archive.infolist():
        name = member.filename.replace('\\', '/')
        path = PurePosixPath(name)
        if (not name or '\x00' in name or path.is_absolute() or '..' in path.parts
                or ':' in name or not path.parts):
            raise ValueError(f'Unsafe archive member: {member.filename}')
        if stat.S_ISLNK(member.external_attr >> 16):
            raise ValueError(f'Archive contains a symbolic link: {member.filename}')
        if member.is_dir() and member.file_size:
            raise ValueError(f'Archive directory contains file data: {member.filename}')
        key = name_key(name)
        if key in seen:
            raise ValueError(f'Duplicate archive member: {member.filename}')
        seen.add(key)
        kinds[key] = member.is_dir()
    for name in kinds:
        for parent in PurePosixPath(name).parents:
            if parent.as_posix() in kinds and not kinds[parent.as_posix()]:
                raise ValueError(f'Archive file is also a directory: {parent}')


def authenticate(path, password, *, all_members=False, for_rewrite=False, cancelled=lambda: False):
    """Authenticate by fully reading encrypted data, not just its weak header check."""
    check_cancelled(cancelled)
    with zipfile.ZipFile(path) as headers:
        files = [info for info in headers.infolist() if not info.is_dir()]
        protected = [info for info in files if info.flag_bits & 1]
        if for_rewrite and protected and len(protected) != len(files):
            raise ValueError('Mixed encrypted/plain entries cannot be rewritten safely')
    if not protected:
        # An encrypted directory still needs a password, even without file data.
        if not is_encrypted(path):
            return
    with open_archive(path, password=password) as archive:
        validate_members(archive)
        names = [info.filename for info in archive.infolist() if info.flag_bits & 1]
        if not all_members:
            names = names[:1]
        for name in names:
            with archive.open(name) as stream:
                for _ in iter_chunks(stream, cancelled=cancelled):
                    pass


def archive_manifest(path, *, password=None, cancelled=lambda: False, progress=None):
    """Authenticate every entry and compare decrypted bytes independently of CRCs."""
    with open_archive(path, password=password) as archive:
        validate_members(archive)
        from .rebuilding import content_manifest
        return content_manifest(archive, cancelled=cancelled, progress=progress)


def extract_archive(path, destination, *, password=None, progress=None):
    """Extract at the same root regardless of encryption, with per-file promotion."""
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError('Extraction destination cannot be a symbolic link')
    base = destination.resolve()
    with open_archive(path, password=password) as archive:
        validate_members(archive)
        members = archive.infolist()
        # Resolve all destination paths before creating any entry.
        for info in members:
            target = destination / info.filename.replace('\\', '/')
            if not target.resolve().is_relative_to(base):
                raise ValueError(f'Archive member escapes destination: {info.filename}')
            if target.is_symlink():
                raise ValueError(f'Extraction target is a symbolic link: {info.filename}')
        destination.mkdir(parents=True, exist_ok=True)
        total = sum(info.file_size for info in members if not info.is_dir())
        written = 0
        for info in members:
            target = destination / info.filename.replace('\\', '/')
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with NamedTemporaryFile(dir=target.parent, prefix='.part_', delete=False) as output:
                    temporary = Path(output.name)
                    with archive.open(info) as incoming:
                        while chunk := incoming.read(CHUNK_SIZE):
                            output.write(chunk)
                            written += len(chunk)
                            if progress and total:
                                progress(int(written / total * 100))
                os.replace(temporary, target)
                temporary = None
                try:
                    import datetime, time
                    timestamp = time.mktime(datetime.datetime(*info.date_time).timetuple())
                    os.utime(target, (timestamp, timestamp))
                except (OSError, ValueError, OverflowError):
                    pass
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        if progress:
            progress(100)


def directory_entries(source, *, keep_root=True, cancelled=lambda: False):
    """Plan names without following links; preserve subfolders and empty folders."""
    source = Path(source)
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f'Source must be an ordinary directory: {source}')
    base = source.parent if keep_root else source
    def failed(error):
        raise error
    for root, directories, files in os.walk(source, followlinks=False, onerror=failed):
        check_cancelled(cancelled)
        root = Path(root)
        for name in directories + files:
            if (root / name).is_symlink():
                raise ValueError(f'Cannot archive symbolic links: {root / name}')
        if keep_root or root != source:
            yield root, root.relative_to(base).as_posix() + '/'
        for name in files:
            path = root / name
            if not path.is_file():
                raise ValueError(f'Cannot archive a nonregular file: {path}')
            yield path, path.relative_to(base).as_posix()


def write_directory(source, destination, *, password=None, keep_root=True):
    from tempfile import TemporaryDirectory
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if destination == source or source in destination.parents:
        raise ValueError('The output archive must be outside the source directory')
    if destination.is_symlink():
        raise ValueError('Output archive cannot be a symbolic link')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.commonutils-zip-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'archive.zip'
        create_archive([source], staged, password=password, keep_root=keep_root)
        os.replace(staged, destination)


def create_archive(sources, destination, *, password=None, keep_root=True,
                   compression=zipfile.ZIP_DEFLATED, compresslevel=None,
                   progress=lambda done, total, message: None, cancelled=lambda: False):
    """Create a verified separate ZIP atomically; never delete or replace sources.

    Each selected folder keeps its root. Overlapping selections are deduplicated;
    colliding names, symlinks, unsafe entries and outputs inside sources fail.
    """
    check_cancelled(cancelled)
    progress(0, 0, 'Assessing selected files…')
    sources = tuple(dict.fromkeys(Path(os.path.abspath(path)) for path in sources))
    destination = Path(os.path.abspath(destination))
    if not sources:
        raise ValueError('Select at least one file or folder')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f'Output already exists: {destination}')
    roots = []
    for path in sources:
        check_cancelled(cancelled)
        if path.is_symlink() or not path.exists():
            raise ValueError(f'Source must exist and cannot be a symbolic link: {path}')
        if destination.resolve() == path.resolve() or (path.is_dir() and destination.resolve().is_relative_to(path.resolve())):
            raise ValueError('The output archive must be outside the selected sources')
        if not any(parent != path and parent.is_dir() and path.is_relative_to(parent) for parent in sources):
            roots.append(path)
    entries = []
    for root in roots:
        check_cancelled(cancelled)
        if root.is_dir():
            entries.extend(directory_entries(root, keep_root=keep_root, cancelled=cancelled))
        elif root.is_file():
            entries.append((root, root.name))
        else:
            raise ValueError(f'Cannot archive a nonregular file: {root}')
    names = set()
    signatures = {}
    expected = {}
    total_bytes = sum(path.stat().st_size for path, name in entries if path.is_file())
    done = 0
    def advanced(size, message):
        nonlocal done
        done += size
        progress(done, 3 * total_bytes, message)
    for path, name in entries:
        check_cancelled(cancelled)
        key = name_key(name)
        if key in names:
            raise ValueError(f'Selected sources have colliding archive names: {name}')
        names.add(key)
        signatures[path] = path.stat()
        if path.is_dir():
            expected[name] = None
        else:
            with path.open('rb') as source:
                expected[name] = stream_signature(source, cancelled=cancelled,
                                                  progress=lambda size: advanced(size, f'Checking {name}'))
    def signature(stat):
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
    destination.parent.mkdir(parents=True, exist_ok=True)
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix='.logistics-zip-', dir=destination.parent) as temp:
        staged = Path(temp) / 'result.zip'
        with open_archive(staged, 'w', password=password, compression=compression, compresslevel=compresslevel) as archive:
            for path, name in entries:
                check_cancelled(cancelled)
                if path.is_symlink() or signature(path.stat()) != signature(signatures[path]):
                    raise RuntimeError(f'Source changed while archiving: {path}')
                info = copy_member_info(zipfile.ZipInfo.from_file(path, name), archive)
                info.compress_type = archive.compression
                info._compresslevel = compresslevel
                if path.is_dir():
                    archive.writestr(info, b'')
                else:
                    with path.open('rb') as incoming, archive.open(info, 'w', force_zip64=True) as output:
                        copy_stream(incoming, output, cancelled=cancelled,
                                    progress=lambda size: advanced(size, f'Creating ZIP: {name}'))
        progress(done, 3 * total_bytes, 'Verifying encrypted ZIP…')
        if archive_manifest(staged, password=password, cancelled=cancelled,
                            progress=lambda count, total, message: progress(2 * total_bytes + count,
                                                                           3 * total_bytes, message)) != expected:
            raise ValueError('Archive verification failed; no output was published')
        for path, before in signatures.items():
            check_cancelled(cancelled)
            if path.is_symlink() or signature(path.stat()) != signature(before):
                raise RuntimeError(f'Source changed while archiving: {path}')
        # Windows _commit requires a writable descriptor, even after ZIP close.
        with staged.open('r+b') as stream:
            os.fsync(stream.fileno())
        # Exclusive link prevents replacing an output created by another operation.
        progress(3 * total_bytes, 3 * total_bytes, f'Publishing verified ZIP: {destination}')
        check_cancelled(cancelled)
        os.link(staged, destination)
    return destination
