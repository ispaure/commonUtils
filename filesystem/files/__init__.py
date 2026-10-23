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
from pathlib import Path
from shutil import rmtree, copyfile, copy2
import csv

# Common utilities
from ...runtime.platform import *
import os
from ...runtime.diagnostics import *


delete_debug_prompt: bool = False


from .. import FilesystemObject
from ..local_access import check_local_path


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
        check_local_path(self.path)
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

        Returns True when no existing regular file needs a permission change.
        Raises PermissionError / OSError on failure.
        """
        p = Path(self.path)
        check_local_path(p)

        if not p.exists() or not p.is_file():
            return True

        match get_os():
            case OS.MAC | OS.LINUX | OS.IOS | OS.ANDROID:
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
        check_local_path(self.path)
        from ...integrations.wrappers import cmdShellWrapper
        tool_name = 'MacOS Permission'
        # App Run permissions
        log(Severity.DEBUG, tool_name, f'Getting CHMOD+X Permission for "{self.path}"')
        # Absolute argv keeps names literal and prevents option-like filenames
        # from becoming chmod flags; the native tool retains its umask policy.
        result = cmdShellWrapper.run_command(['chmod', '+x', str(self.path.absolute())],
                                            idle_timeout=15, shell=False)
        if not result.success:
            detail = '\n'.join(result.lines) or f'exit status {result.returncode}'
            raise OSError(f'Could not make "{self.path}" executable: {detail}')


    def copy_file(self, destination: Union[str, Path]) -> "File":
        """Copy to a destination and return its fresh File snapshot. I/O errors propagate.

        The original object is not retargeted; cached metadata remains a snapshot.
        """
        source = self.path
        destination = Path(destination)
        check_local_path(source)
        check_local_path(destination)
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
        check_local_path(original_name, recursive=True)
        check_local_path(new_name, recursive=True)
        from ..rename import rename_path
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
        check_local_path(src)
        check_local_path(dest)
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
                from ..snapshots import copy_content_state, file_revision
                from ...persistence.transfers import verify_unchanged, cleanup_published
                before = file_revision(src, follow_symlinks=False)
                def validate():
                    verify_unchanged(before, lambda: file_revision(src, follow_symlinks=False), error=OSError,
                                     message='Source changed during moving; it has been preserved.')
                try:
                    expected = copy_content_state(src)
                    copy2(src, staged_file, follow_symlinks=False)
                    verify_unchanged(expected, lambda: copy_content_state(staged_file), error=OSError,
                                     message='Copied content verification failed; source preserved.')
                except ValueError as error:
                    raise OSError('Could not verify file contents; source preserved.') from error
                validate()
                os.replace(staged_file, dest)
            def remove():
                validate()
                src.unlink()
            cleanup_published(remove, source_state=lambda: 'unchanged'
                              if file_revision(src, follow_symlinks=False) == before else 'unknown')

        return File(dest)


def has_subdirectories(path: Path) -> bool:
    return any(item.is_dir() for item in path.iterdir())


def get_split_character():
    match get_os():
        case OS.WIN:
            return '\\'
        case OS.MAC | OS.LINUX | OS.IOS | OS.ANDROID:
            return '/'


def get_current_working_dir() -> Path:
    current_file = os.path.abspath(__file__)
    cwd = Path(current_file).parents[3]
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
