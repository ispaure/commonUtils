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
from shutil import make_archive

# Compression utilities
import patoolib
import zipfile

# Common utilities
from .. import fileUtils
from ..debugUtils import *


def unzip_file(source_file: Union[str, Path],
               destination_dir: Union[str, Path],
               pwd: Optional[str] = None,
               show_progress: bool = False) -> bool:
    """Compatibility wrapper: validated streaming extraction for plain/AES ZIPs.

    Passwords are explicit; this utility never prompts. Failure returns False,
    incomplete entries are removed, and callers retain ownership of the workspace.
    """
    from ..zip_access import extract_archive
    progress_window = None
    try:
        if show_progress:
            from .. import ui
            progress_window = ui.pyside.display_progress_bar(f'Extracting {Path(source_file).name}')
        extract_archive(source_file, destination_dir, password=pwd,
                        progress=progress_window.update_progress if progress_window else None)
        return True
    except Exception as error:
        log(Severity.ERROR, 'Extract ZIP File', f'Could not extract "{source_file}": {error}')
        return False
    finally:
        if progress_window is not None:
            progress_window.dlg.close()


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
        log(Severity.DEBUG, tool_name, f'Extracting archive from "{source_file}" to "{destination_dir}"')
        patoolib.extract_archive(source_file, outdir=destination_dir)
    else:
        log(Severity.DEBUG, tool_name, f'Extracting archive from "{source_file}" to "{destination_dir}"')
        patoolib.extract_archive(source_file, outdir=destination_dir, program=unrar_sw_path)

    # TODO: Doesn't work for macos because cant find software. Need program= flag with proper software
    # TODO: Or alternate solution is interfacing with Keka through Commandline perhaps?: https://github.com/aonez/Keka/wiki/Terminal-support


def zip_file(source: Union[str, Path], destination: Union[str, Path], keep_root=True, *, password=None):
    """
    Create a zip file from the source to the destination.
    :param source: Source path to compress
    :type source: Union[str, Path]
    :param destination: Destination path of compressed archive (incl. extension)
    :type destination: Union[str, Path]
    :param keep_root: When source is a dir, keeps the dir as part of the archive as a root folder (Default true)
    :type keep_root: bool
    """

    if password is not None:
        from ..zip_access import write_directory
        return write_directory(source, destination, password=password, keep_root=keep_root)

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
        else:
            # If desired extension is not zip, create a zip regardless and then rename to extension we want
            # (but throw error if there is zip at that location already)
            if_was_zip_path = f'{destination_str[:-len(ext) - 1]}.zip'
            if os.path.exists(if_was_zip_path):
                log(Severity.CRITICAL, 'zipUtils.zip_file',
                    f'Trying to overwrite file which should not be overwritten!: {if_was_zip_path}')
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
