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
import stat
import subprocess
from pathlib import Path
from shutil import rmtree, copyfile, move
import csv

# Common utilities
from .osUtils import *
from .debugUtils import *
from .wrappers import cmdShellWrapper


match get_os():
    case OS.LINUX:
        import pwd


delete_debug_prompt: bool = False


class File:
    def __init__(self, path: Path):
        self.path = path
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

class TXTFile(File):
    """
    Deprecated; point to fileTypes.txtType instead.
    """
    def __init__(self, path: Path):
        super().__init__(path)
        self.line_lst = []

    def read_lines(self) -> List[str]:
        """
        Import the lines from the text file into self.line_lst
        """
        with open(self.path, "r", encoding="utf-8-sig") as f:
            self.line_lst = f.read().splitlines()
        return self.line_lst

    def write_lines(self, path: Union[Path, None] = None):
        """
        Export self.line_lst to the given path if provided (else use the current file path)
        """
        # Ensures there is no \n in lines (exporter already takes care of that). Critical error if that's the case.
        for i, line in enumerate(self.line_lst):
            if "\n" in line:
                log(Severity.CRITICAL,
                    "TXTFile.export",
                    f"Slash N found in export on line {i}: {repr(line)}. "
                    "Please resolve upstream (exporter adds newlines automatically).")

        # Get export path
        export_path = path or self.path

        # Make export dir (if missing)
        export_dir = export_path.parent
        export_dir.mkdir(parents=True, exist_ok=True)

        # Ensure file writable if exists
        self.make_writable()

        # Write file
        with open(export_path, "w", encoding="utf-8") as f:
            for i, line in enumerate(self.line_lst):
                if i < len(self.line_lst) - 1:
                    f.write(f"{line}\n")
                else:
                    f.write(line)

    def edit_in_default_editor(self):
        path_str = str(self.path)

        match get_os():
            case OS.WIN:
                subprocess.run(["start", "", path_str], shell=True)
            case OS.MAC:
                result = subprocess.run(["open", path_str], capture_output=True)
                if result.returncode != 0:
                    # Fallback to TextEdit
                    subprocess.Popen(["open", "-a", "TextEdit", path_str])
            case OS.LINUX:
                subprocess.run(["xdg-open", path_str])


def move_file(src: Path, dest: Path) -> bool:
    """
    Moves a file from src to dest, overwriting if it already exists.
    Returns True if successful, False otherwise.
    """
    src = Path(src)
    dest = Path(dest)

    try:
        # Ensure destination folder exists
        dest.parent.mkdir(parents=True, exist_ok=True)

        # If destination exists, delete it first
        if dest.exists():
            dest.unlink()

        # Move the file
        log(Severity.DEBUG, 'fileUtils.move_file', f'Moving file from \"{src}\" to \"{dest}\"')
        move(str(src), str(dest))

        # Verify move succeeded
        if dest.exists() and not src.exists():
            return True
        else:
            log(Severity.CRITICAL, 'fileUtils.move_file', f'Move may have failed: src exists={src.exists()}, dest exists={dest.exists()}')
            return False

    except Exception as e:
        log(Severity.CRITICAL, 'fileUtils.move_file', f'Error moving file from \"{src}\" to \"{dest}\": {e}')
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
    """
    Renames a file on disk.
    If `force` is True, and the destination exists, it will be deleted first.
    Returns True if successful, False otherwise.
    """
    original_name = Path(original_name)
    new_name = Path(new_name)

    try:
        # If forced overwrite and destination exists on Windows
        if force and sys.platform == 'win32' and new_name.exists():
            File(new_name).delete_file()

        # Ensure parent directory for new file exists
        new_name.parent.mkdir(parents=True, exist_ok=True)

        # Perform rename
        log(Severity.DEBUG, 'fileUtils.rename_file', f'Renaming file from "{original_name}" to "{new_name}"')
        os.rename(original_name, new_name)

        # Verify success
        if new_name.exists() and not original_name.exists():
            return True
        else:
            log(Severity.WARNING, 'fileUtils.rename_file',
                f'Rename may have failed: original exists={original_name.exists()}, new exists={new_name.exists()}')
            return False

    except Exception as e:
        log(Severity.ERROR, 'fileUtils.rename_file',
            f'Error renaming file from "{original_name}" to "{new_name}": {e}')
        return False


def copy_file(source: Union[str, Path], destination: Union[str, Path]) -> bool:
    """
    Copy a file from source to destination.

    Returns:
        True if the file was copied successfully.
        False if the copy failed.
    """
    source = Path(source)
    destination = Path(destination)

    try:
        # Create the destination directory if necessary
        make_dir(destination.parent)

        log(Severity.DEBUG, 'fileUtils.copy_file', f'Copying file from "{source}" to "{destination}"')

        copyfile(source, destination)
        return True

    except (OSError, IOError) as error:
        log(Severity.ERROR, 'fileUtils.copy_file', f'Failed to copy file from "{source}" to "{destination}": {error}')
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
    cwd = Path(current_file).parent.parent
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
