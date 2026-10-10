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
import errno
import stat
from tempfile import TemporaryDirectory
import subprocess
from pathlib import Path
from shutil import rmtree, copyfile, copy2
import csv

# Common utilities
from ..osUtils import *
from ..debugUtils import *
from ..wrappers import cmdShellWrapper


match get_os():
    case OS.LINUX:
        import pwd


delete_debug_prompt: bool = False


from ..filesystem import FilesystemObject


class File(FilesystemObject):
    def __init__(self, path: Path):
        self.path = Path(path)
        self.file_name = self.__get_file_name()
        self.name_without_ext = self.__get_name_without_ext()
        self.ext: Union[str, None] = self.__get_ext()
        self.size: Union[int, None] = self.__get_size()

    def __get_file_name(self) -> str:
        return self.path.name

    def __get_name_without_ext(self) -> str:
        """Return the file name without extension."""
        return self.path.stem

    def __get_ext(self) -> Union[str, None]:
        """Return the file extension (without the dot). And always lower"""
        if self.path.suffix:
            ext = self.path.suffix.lstrip('.')
            return ext.lower()
        else:
            return None

    def __get_size(self) -> Union[int, None]:
        """Return the file size in bytes, or None if file does not exist."""
        try:
            return self.path.stat().st_size
        except FileNotFoundError:
            return None

    def delete_file(self, make_writable: bool = False) -> bool:
        """
        Deletes the file on disk.

        By default, file permissions are not modified before deletion.
        If make_writable is True and deletion fails due to permissions,
        the file is made writable and deletion is attempted again.

        Returns True if successfully deleted.
        Raises a CRITICAL error if deletion fails.

        macOS AppleDouble files starting with "._" are treated as successfully deleted
        if they disappear before the delete operation completes.
        """
        if delete_debug_prompt:
            log(Severity.WARNING, 'Delete File', f'Deleting "{self.path}", proceed?', popup=True)

        try:
            os.remove(self.path)

        except FileNotFoundError as e:
            if self.path.name.startswith('._'):
                return True

            log(Severity.CRITICAL, 'Delete File', f'Could not delete "{self.path}"\n{type(e).__name__}: {e}')

        except PermissionError as e:
            if not make_writable:
                log(Severity.CRITICAL, 'Delete File', f'Could not delete "{self.path}" due to permissions\n{type(e).__name__}: {e}')

            try:
                self.make_writable()
                os.remove(self.path)
            except Exception as retry_error:
                log(Severity.CRITICAL, 'Delete File', f'Could not delete "{self.path}" after making it writable\n{type(retry_error).__name__}: {retry_error}')

        except Exception as e:
            log(Severity.CRITICAL, 'Delete File', f'Could not delete "{self.path}"\n{type(e).__name__}: {e}')

        if self.path.exists():
            log(Severity.CRITICAL, 'Delete File', f'File still exists after deletion attempt: "{self.path}"')

        return True

    def make_writable(self) -> bool:
        """
        Ensures the file is writable by the owner, without removing any
        existing permissions.

        Returns False if the file does not exist.
        Raises PermissionError / OSError on failure.
        """
        p = Path(self.path)

        if not p.exists() or not p.is_file():
            return True

        match get_os():
            case OS.MAC | OS.LINUX:
                st = os.stat(p)
                if not (st.st_mode & stat.S_IWUSR):
                    os.chmod(p, st.st_mode | stat.S_IWUSR)

            case OS.WIN:
                # Best-effort: clear read-only attribute
                st = os.stat(p)
                if not (st.st_mode & stat.S_IWRITE):
                    os.chmod(p, st.st_mode | stat.S_IWRITE)

            case _:
                raise RuntimeError("Unsupported OS")

        return True

    def set_executable_permission(self):
        """
        For macOS / Linux, gets permission of a file to be an executable. Helpful if a file won't run or open
        """
        tool_name = 'MacOS Permission'
        # App Run permissions
        log(Severity.DEBUG, tool_name, f'Getting CHMOD+X Permission for "{self.path}"')
        cmdShellWrapper.exec_cmd(f'chmod +x "{self.path}"')


    def copy_file(self, destination: Union[str, Path]) -> "File":
        """Copy to a destination and return its fresh File snapshot. I/O errors propagate.

        The original object is not retargeted; cached metadata remains a snapshot.
        """
        source = self.path
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        log(Severity.DEBUG, 'fileUtils.copy_file', f'Copying file from "{source}" to "{destination}"')

        copyfile(source, destination)
        return File(destination)

    def rename_file(self, destination: Union[str, Path], force: bool = False) -> "File":
        """Rename and return a fresh File; preserve destinations unless force=True.

        The original object is not retargeted; cached metadata remains a snapshot.
        """
        original_name = self.path
        new_name = Path(destination)
        from ..renameUtils import rename_path
        new_name.parent.mkdir(parents=True, exist_ok=True)
        log(Severity.DEBUG, 'fileUtils.rename_file', f'Renaming file from "{original_name}" to "{new_name}"')
        rename_path(original_name, new_name, overwrite=force)
        return File(new_name)

    def move_file(self, destination: Union[str, Path]) -> "File":
        """Move with the existing atomic/cross-volume policy and return a fresh File.

        The original object is not retargeted; cached metadata remains a snapshot.
        """
        src = self.path
        dest = Path(destination)
        if not src.is_file():
            raise FileNotFoundError(f'Source is not an existing file: "{src}"')

        if dest.exists() and src.samefile(dest):
            return File(dest)

        dest.parent.mkdir(parents=True, exist_ok=True)
        log(Severity.DEBUG, 'fileUtils.move_file', f'Moving file from "{src}" to "{dest}"')

        try:
            os.replace(src, dest)
        except OSError as error:
            if error.errno != errno.EXDEV:
                raise

            # Copy completely on the destination filesystem before replacing
            # its previous contents. Failed copies leave both files intact.
            with TemporaryDirectory(dir=dest.parent, prefix='.move_') as staging_dir:
                staged_file = Path(staging_dir) / 'file'
                copy2(src, staged_file, follow_symlinks=False)
                os.replace(staged_file, dest)
            src.unlink()

        return File(dest)


def move_file(src: Path, dest: Path) -> bool:
    """Compatibility function: boolean outcome; new callers use File.move_file."""
    try:
        File(src).move_file(dest)
        return True
    except Exception as error:
        log(Severity.ERROR, 'fileUtils.move_file', f'Could not move_file from "{src}" to "{dest}": {error}')
        return False


def has_subdirectories(path: Path) -> bool:
    return any(item.is_dir() for item in path.iterdir())


def get_split_character():
    match get_os():
        case OS.WIN:
            return '\\'
        case OS.MAC | OS.LINUX:
            return '/'


def rename_file(original_name: Path, new_name: Path, force: bool = False) -> bool:
    """Compatibility function: boolean outcome; new callers use File.rename_file."""
    try:
        File(original_name).rename_file(new_name, force=force)
        return True
    except Exception as error:
        log(Severity.ERROR, 'fileUtils.rename_file', f'Could not rename_file from "{original_name}" to "{new_name}": {error}')
        return False


def copy_file(source: Union[str, Path], destination: Union[str, Path]) -> bool:
    """Compatibility function: boolean outcome; new callers use File.copy_file."""
    try:
        File(source).copy_file(destination)
        return True
    except (OSError, IOError) as error:
        log(Severity.ERROR, 'fileUtils.copy_file', f'Could not copy_file from "{source}" to "{destination}": {error}')
        return False


def make_dir(directory):
    """
    Creates directory at location (if it doesn't exist)
    DEPRECATED: Fix any usage by swapping to Directory.make_dir() instead.
    """
    log(Severity.WARNING, 'fileUtils.make_dir', 'This function is deprecated! Use dirUtils.Directory.make_dir instead.')
    if not os.path.exists(directory):
        log(Severity.DEBUG, 'fileUtils.make_dir', f'Creating Directory at "{directory}"')
        Path(directory).mkdir(parents=True, exist_ok=True)


def get_current_working_dir() -> Path:
    current_file = os.path.abspath(__file__)
    cwd = Path(current_file).parents[2]
    cwd_resolved = Path.resolve(cwd)
    return cwd_resolved


def get_user_home_dir() -> Path:
    """
    Get the current user's home directory
    """
    return Path.home()


def get_user_name() -> str:
    return Path(get_user_home_dir()).name


def get_user_lib_dir() -> Path:
    return Path(get_user_home_dir(), 'Library')


def get_user_application_support() -> Path:
    return Path(get_user_lib_dir(), 'Application Support')


def get_user_appdata_roaming() -> Path:
    return Path(os.environ.get('APPDATA'))


def get_user_appdata_local() -> Path:
    return Path(os.environ.get('LOCALAPPDATA'))
