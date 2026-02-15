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

from typing import *
from pathlib import Path
import os
import sys
import stat
import shutil
import subprocess
from shutil import make_archive
import zlib
from tempfile import NamedTemporaryFile

# Compression utilities
import pyzipper
import patoolib
import zipfile

# Common utilities
from . import fileUtils
from .debugUtils import *


class ZIPFile(fileUtils.File):
    def __init__(self, path: Path):
        # Call the parent (File) initializer
        super().__init__(path)

    def extract(self, dest_path: Path) -> bool:
        """Extract the CBZ File"""
        return unzip_file(self.path, dest_path)

    def get_root_file_lst(self) -> List[str]:
        try:
            with zipfile.ZipFile(self.path, 'r') as zip_ref:
                # list of all entries at root (no '/')
                return [Path(f).name for f in zip_ref.namelist() if '/' not in f]
        except zipfile.BadZipFile:
            log(Severity.CRITICAL, "CBZFile", f"Invalid ZIP structure in {self.path}")


def unzip_file(source_file: Union[str, Path],
               destination_dir: Union[str, Path],
               pwd: Optional[str] = None) -> bool:
    """
    Extracts zip file to desired location.
    Returns True iff all entries extract & CRC-verify; otherwise False.

    NOTE: Encrypted-archive handling is intentionally unchanged.
    """
    tool_name = 'Extract ZIP File'

    # Normalize inputs
    if isinstance(source_file, (str, Path)):
        source_file_str = str(source_file)
    else:
        log(Severity.ERROR, tool_name, 'Wrong Input type for Source File')
        return False

    if isinstance(destination_dir, (str, Path)):
        destination_dir_str = str(destination_dir)
    else:
        log(Severity.ERROR, tool_name, 'Wrong Input type for Destination Directory')
        return False

    # Helper: robust "is inside" check (prevents Zip Slip)
    def _is_within(base: Path, target: Path) -> bool:
        try:
            base_resolved = base.resolve()
            target_resolved = target.resolve()
            return os.path.commonpath([str(base_resolved), str(target_resolved)]) == str(base_resolved)
        except Exception:
            return False

    # ---- Unencrypted ---------------------------------------------------------
    if pwd is None:
        log(Severity.DEBUG, tool_name, f'Extracting archive from "{source_file_str}" to "{destination_dir_str}"')

        src = Path(source_file_str)
        dest = Path(destination_dir_str)

        try:
            dest.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(src, 'r') as zf:
                for info in zf.infolist():
                    # Directories
                    if info.is_dir():
                        (dest / info.filename).mkdir(parents=True, exist_ok=True)
                        continue

                    # Optional: skip Unix symlinks for safety
                    is_unix_symlink = (info.create_system == 3) and (
                        stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK
                    )
                    if is_unix_symlink:
                        log(Severity.WARNING, tool_name, f"Skipping symlink entry: {info.filename}")
                        continue

                    # Destination path for this member
                    target_path = (dest / info.filename)

                    # Path traversal guard
                    if not _is_within(dest, target_path):
                        log(Severity.ERROR, tool_name, f"[SECURITY] Skipping suspicious path: {info.filename}")
                        return False

                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    # Stream to a temp file; CRC enforced by fully consuming the stream
                    with NamedTemporaryFile(delete=False, dir=target_path.parent, prefix=".part_") as tmp:
                        tmp_name = tmp.name
                        try:
                            with zf.open(info, 'r') as src_f:
                                # Hint types to silence IDE warning about copyfileobj
                                shutil.copyfileobj(
                                    cast(BinaryIO, src_f),
                                    cast(BinaryIO, tmp),
                                    length=1024 * 1024  # 1 MiB chunks
                                )
                        except (zipfile.BadZipFile, zlib.error, OSError, RuntimeError) as e:
                            # Clean up partial
                            try:
                                os.unlink(tmp_name)
                            except OSError:
                                pass
                            log(Severity.ERROR, tool_name, f"[CRC/READ FAIL] {info.filename}: {e}")
                            return False

                    # Atomic move into place only if read (and CRC) succeeded
                    os.replace(tmp_name, target_path)

                    # (Optional) Preserve mtime from ZIP entry
                    try:
                        import datetime, time
                        dt = datetime.datetime(*info.date_time)  # local time tuple
                        ts = int(time.mktime(dt.timetuple()))
                        os.utime(target_path, (ts, ts))
                    except Exception:
                        pass

            return True

        except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError) as e:
            log(Severity.ERROR, tool_name, f"[ZIP FAIL] {src}: {e}")
            return False

    # ---- Encrypted (left as-is by request) -----------------------------------
    else:
        log(Severity.DEBUG, tool_name, f'Extracting password-protected archive from "{source_file_str}" to "{destination_dir_str}"')

        # # Legacy ZIP 2.0 only (left commented on purpose)
        # with zipfile.ZipFile(source_file_str, 'r') as zip_ref:
        #     zip_ref.extractall(path=destination_dir_str, members=None, pwd=pwd.encode())

        # AES/ZIP 2.0 via pyzipper (UNCHANGED BEHAVIOR)
        with pyzipper.AESZipFile(source_file_str, 'r',
                                 compression=pyzipper.ZIP_DEFLATED,
                                 encryption=pyzipper.WZ_AES) as extracted_zip:
            extracted_zip.extractall(path=destination_dir_str, pwd=str.encode(pwd))
        return True


def unrar_file(source_file, destination_dir, unrar_sw_path: str = None):
    """
    Extracts rar file to desired location.
    :param source_file: Path to file to extract.
    :type source_file: str
    :param destination_dir: Directory to extract into.
    :type destination_dir: str
    :param unrar_sw_path: Path to the unrar software (for macOS)
    :type unrar_sw_path: str
    """
    tool_name = 'Extract RAR File'
    if sys.platform == 'win32':
        log(Severity.DEBUG, Severity.DEBUG, f'Extracting archive from "{source_file}" to "{destination_dir}"')
        patoolib.extract_archive(source_file, outdir=destination_dir)
    else:
        log(Severity.DEBUG, Severity.DEBUG, f'Extracting archive from "{source_file}" to "{destination_dir}"')
        patoolib.extract_archive(source_file, outdir=destination_dir, program=unrar_sw_path)
    # TODO: Doesn't work for macos because cant find software. Need program= flag with proper software
    # TODO: Or alternate solution is interfacing with Keka through Commandline perhaps?: https://github.com/aonez/Keka/wiki/Terminal-support


def zip_file(source: Union[str, Path], destination: Union[str, Path], keep_root=True):
    """
    Create a zip file from the source to the destination.
    :param source: Source path to compress
    :type source: Union[str, Path]
    :param destination: Destination path of compressed archive (incl. extension)
    :type destination: Union[str, Path]
    :param keep_root: When source is a dir, keeps the dir as part of the archive as a root folder (Default true)
    :type keep_root: bool
    """
    def make_zipfile_keep_root(output_filename, source_dir):
        relroot = os.path.abspath(os.path.join(source_dir, os.pardir))
        with zipfile.ZipFile(output_filename, "w", zipfile.ZIP_DEFLATED) as zip:
            for root, dirs, files in os.walk(source_dir):
                # add directory (needed for empty dirs)
                zip.write(root, os.path.relpath(root, relroot))
                for file in files:
                    filename = os.path.join(root, file)
                    if os.path.isfile(filename):  # regular files only
                        arcname = os.path.join(os.path.relpath(root, relroot), file)
                        zip.write(filename, arcname)

    def make_zipfile_discard_root(source_str, destination_str):
        # Determine suffix
        destination_path = Path(destination_str)
        if destination_path.suffix:
            ext = destination_path.suffix.lstrip('.')
            ext = ext.lower()
        else:
            log(Severity.CRITICAL, 'zipUtils.zip_file', 'Destination path does not have an extension!')
            sys.exit()
        if ext == 'zip':
            log(Severity.DEBUG, 'zipUtils.zip_file', f'Creating Archive: {destination_path}')
            make_archive(destination_str[:-len('.zip')], 'zip', source_str)
        else:  # If desired extension is not zip, create a zip regardless and then rename to extension we want (but throw error if there is zip at that location already)
            if_was_zip_path = f'{destination_str[:-len(ext) - 1]}.zip'
            if os.path.exists(if_was_zip_path):
                log(Severity.CRITICAL, 'zipUtils.zip_file', f'Trying to overwrite file which should not be overwritten!: {if_was_zip_path}')
                sys.exit()
            else:
                log(Severity.DEBUG, 'zipUtils.zip_file', f'Creating Archive: {if_was_zip_path}')
                make_archive(destination_str[:-len(ext) - 1], 'zip', source_str)
                fileUtils.move_file(Path(if_was_zip_path), destination_path)

    if isinstance(source, str):
        source_str = source
    elif isinstance(source, Path):
        source_str = str(source)
    else:
        log(Severity.CRITICAL, 'zipUtils.zip_file', 'Source is not a string or Path!')
        sys.exit()

    if isinstance(destination, str):
        destination_str = destination
    elif isinstance(destination, Path):
        destination_str = str(destination)
    else:
        log(Severity.CRITICAL, 'zipUtils.zip_file', 'Destination is not a string or Path!')
        sys.exit()

    if keep_root:
        make_zipfile_keep_root(destination_str, source_str)
    else:
        make_zipfile_discard_root(source_str, destination_str)
