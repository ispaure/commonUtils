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
import os
import sys
import stat
import subprocess
from pathlib import Path
from shutil import rmtree, copyfile, move

# Common utilities
from .osUtils import *
from .debugUtils import *
from .wrappers import cmdShellWrapper


match get_os():
    case OS.WIN:
        from . import junctionUtils
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

    def delete_file(self) -> bool:
        if delete_debug_prompt:
            log(Severity.WARNING, 'Delete File', f'Deleting "{self.path}", proceed?', popup=True)
        result = delete_file(self.path)
        return result


class TXTFile(File):
    def __init__(self, path: Path):
        super().__init__(path)
        self.line_lst = []

    def import_line_lst(self) -> List[str]:
        """
        Import the lines from the text file into self.line_lst
        """
        with open(self.path, "r", encoding="utf-8-sig") as f:
            self.line_lst = f.read().splitlines()
        return self.line_lst

    def export(self, path: Union[Path, None] = None):
        """
        Export self.line_lst to the given path if provided (else use the current file path)
        """
        export_path = path or self.path

        with open(export_path, "w", encoding="utf-8") as f:
            for i, line in enumerate(self.line_lst):
                if i < len(self.line_lst) - 1:
                    f.write(f"{line}\n")
                else:
                    f.write(line)


def hang_n_terminate():
    """
    Hangs the script, quits on keypress
    :return:
    """
    input('Dev-implemented break point! Press key to exit!')
    sys.exit()


def get_file_path_list(dir_name: Union[str, Path], recursive=True, filter_extension=None) -> List[str]:
    """
    Returns list of all files under a specific directory. Properly sorted

    Input example:
    root/
    ├── b.txt
    ├── z.txt
    ├── a_folder/
    │   └── a.txt
    └── z_folder/
        └── z.txt

    Output example:
    root/b.txt
    root/z.txt
    root/a_folder/a.txt
    root/z_folder/z.txt

    This is what we often want (root files first, then files in folders in order).
    Note: Does not sort well 1, 10, 11 type stuff (work well with 01, 10, 11!)
    So if required, add padding before sorting.

    :param dir_name: Directory in which to look under
    :type dir_name: str
    :param recursive: Indicate if sub-directories should be included, recursively
    :param filter_extension: File extension to retain (when just want to retain all .txt files for example)
    :type filter_extension: str
    :rtype: lst
    """
    # create a list of file and subdirectories
    # names in the given directory
    list_of_files = sorted(os.listdir(dir_name))  # Ensures alphabetical sorting

    all_files = list()
    # Iterate over all the entries
    for entry in list_of_files:
        # Create full path
        full_path = os.path.join(dir_name, entry)
        # If entry is a directory then get the list of files in this directory
        if os.path.isdir(full_path):
            if recursive:
                all_files = all_files + get_file_path_list(full_path)
        else:
            all_files.append(full_path)

    # If set a file type filter, filter.
    if filter_extension is not None:
        filtered_files = list()
        for file in all_files:
            if '.' + filter_extension.lower() == file[-len(filter_extension)-1:].lower():
                filtered_files.append(file)
        return filtered_files

    return all_files


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


def read_file(file_path: Union[str, Path]):
    """
    Returns each line of a text file as part of a list.
    :param file_path: File path to read
    :type file_path: str
    :rtype: lst
    """
    log(Severity.WARNING, 'fileUtils.read_file', 'DEPRECATED METHOD IN USE; RESOLVE!')
    txt = TXTFile(file_path)
    txt.import_line_lst()
    return txt.line_lst


def append_line_lst_to_file(line_lst, file_path):
    """
    Appends a list of lines to the end of a file
    """
    for line in line_lst:
        with open(file_path, 'a') as f:
            f.write('\n' + line)


def get_dirs_path_list(dir_path: Union[Path, str]):
    """
    Returns a sorted list of valid directory paths within a directory.
    Function copied from Blue Hole Addon scripts and updated to sort alphabetically.
    :param dir_path: Directory in which to look for directories
    :type dir_path: str | Path
    :rtype: list[str]
    """
    if isinstance(dir_path, str):
        dir_path_str = dir_path
    elif isinstance(dir_path, Path):
        dir_path_str = str(dir_path)
    else:
        print('Wrong type sent to fileUtils.get_dirs_path_list!')
        return None

    dir_path_lst = []
    # Get list of items within a directory
    atlas_sub_dir_item_lst = os.listdir(dir_path_str)
    # Create a path from items within the directory, and if they are a directory, add them to the directories list.
    for item in atlas_sub_dir_item_lst:
        item_dir = str(Path(dir_path_str, item))
        if os.path.isdir(item_dir):
            dir_path_lst.append(item_dir)

    # Sort alphabetically (case-insensitive)
    dir_path_lst.sort(key=lambda s: s.lower())
    return dir_path_lst


def create_n_wipe_dir(path: Path):
    """
    Creates directory at path if it does not exist, also wipes contents and double-check it's fully empty.
    """
    if not os.path.isdir(path):
        make_dir(path)
    if not is_dir_empty(path):
        delete_dir_contents(path)
        # Double-Check that it is empty now
        if not is_dir_empty(path):
            log(Severity.CRITICAL, 'fileUtils.create_n_wipe_dir', f'Could not delete dir contents in {path}')


def has_subdirectories(path: Path) -> bool:
    return any(item.is_dir() for item in path.iterdir())


def delete_dir(dir_path: Path) -> bool:
    """
    Deletes a directory on disk
    """
    if delete_debug_prompt:
        log(Severity.WARNING, 'Delete Directory', f'Deleting "{dir_path}", proceed?', popup=True)
    else:
        log(Severity.DEBUG, 'fileUtils', f'Deleting directory: "{dir_path}"')
    rmtree(dir_path)
    return not os.path.isdir(dir_path)


def delete_dir_contents(dir_path):
    """
    Deletes the files and folders within a directory (not the directory itself)
    """
    # Make sure everything is not marked as non-writable
    for root, dirs, files in os.walk(dir_path):
        for fname in files:
            full_path = os.path.join(root, fname)
            os.chmod(full_path, stat.S_IWRITE)

    # Wipe contents within dir
    rem_dir_lst = get_dirs_path_list(dir_path)
    for rem_dir in rem_dir_lst:
        delete_dir(rem_dir)
    if len(get_dirs_path_list(dir_path)) > 0:
        log(Severity.CRITICAL, 'fileUtils.delete_dir_contents', 'Could not delete every directory!')
    rem_file_lst = get_file_path_list(dir_path)
    for rem_file in rem_file_lst:
        delete_file(rem_file)
    if len(get_file_path_list(dir_path)) > 0:
        log(Severity.CRITICAL, 'fileUtils.delete_dir_contents', 'Could not delete every file!')


def delete_file(file_path) -> bool:
    """
    Deletes a file on disk.
    Returns True if successfully deleted, False otherwise.
    """
    try:
        os.remove(file_path)
        return not os.path.exists(file_path)
    except Exception:
        return False


def delete_symbolic_link(dir_path):
    try:
        os.unlink(dir_path)
    except:
        try:
            os.remove(dir_path)
        except:
            pass


def create_symbolic_link(source_dir, destination_dir):
    """
    Creates a symbolic link from the source dir to the destination dir
    """
    tool_name = 'Create Symbolic Link'

    # Resolve source dir (avoiding potential issues when creating a link)
    if isinstance(source_dir, Path):
        source_dir_resolved = source_dir.resolve()
    elif isinstance(source_dir, str):
        source_dir_path = Path(source_dir)
        source_dir_resolved = source_dir_path.resolve()
    else:
        log(Severity.ERROR, tool_name, 'Source Dir Input is not a Path or string!')
        return

    # If there is no directory within where the symbolic link is supposed to be created, there will be an error.
    # Create directory if required
    if isinstance(destination_dir, Path):
        destination_dir_parent = destination_dir.parent
    elif isinstance(destination_dir, str):
        destination_dir_path = Path(destination_dir)
        destination_dir_parent = destination_dir_path.parent
    else:
        log(Severity.ERROR, tool_name, 'Destination Dir Input is not a Path or string!')
        return
    if not os.path.isdir(destination_dir_parent):
        make_dir(destination_dir_parent)

    os.symlink(source_dir_resolved, destination_dir)


def update_symbolic_link(source: Path, destination: Path, allow_destination_deletion=False):
    """
    Creates a symbolic link (allowing directory deletion if a directory exists at source when specified only)
    If a link already exists, see if it points to the right folder, else updates it.
    """

    # Tool Name
    tool_name = f'Symbolic Link (Update)'
    # Log Message
    msg = f'Source: "{source}"\nDestination: "{destination}"'

    # If source for symbolic link does not exist, abort right now!
    if not os.path.exists(source):
        msg += f'\nSource does not exist; Aborting!'
        log(Severity.ERROR, tool_name, msg)
        return

    # If there is something there other than a symbolic link, wipe it (if authorized)
    if os.path.exists(destination) and not is_symbolic_link(destination):
        if not allow_destination_deletion:
            msg += '\nDestination already exists (And "allow_destination_deletion" is not enabled); Aborting!'
            log(Severity.ERROR, tool_name, msg)
            return
        else:
            if is_junction(destination):
                msg += '\nDestination is junction; unsure how to delete as of yet; Aborting!'
                log(Severity.ERROR, tool_name, msg)
                return
            # elif is_hard_link(destination):
            #     print(f'{tool_name}: Destination is hard link, unsure how to delete as of yet!')
            elif os.path.isfile(destination):
                msg += '\nDestination is a file, not expected for Symbolic Link creation. Aborting!'
                log(Severity.ERROR, tool_name, msg)
                return
            elif is_mount_point(destination):
                msg += '\nDestination is a mount point, unsure how to delete as of yet!'
                # delete_symbolic_link(destination)
                log(Severity.ERROR, tool_name, msg)
                return
            elif is_dir(destination):
                msg += '\nDestination is a directory! Deleting...'
                delete_dir(destination)
            else:
                msg += '\nDestination is unknown type, unsure how to delete as of yet!'
                log(Severity.ERROR, tool_name, msg)
                return

    # If it's a symbolic link, see if path matches expected
    if is_symbolic_link(destination):
        destination_link_path = os.path.realpath(destination)
        if str(Path(destination_link_path)) != str(source):
            msg += '\nSymbolic Link exists at destination, but doesn\'t match expected destination. Updating...'
            # Delete existing link
            delete_symbolic_link(destination)
            # Make a link to the folder
            create_symbolic_link(source, destination)
            log(Severity.DEBUG, tool_name, msg)
        else:
            msg += '\nSymbolic Link Already Up to Date!'
            log(Severity.DEBUG, tool_name, msg)
    else:
        # Create new symbolic link
        msg += '\nSymbolic Link doesn\'t exist at location. Creating...'
        # Make a link to the folder
        create_symbolic_link(source, destination)
        log(Severity.DEBUG, tool_name, msg)


def is_hard_link(path: Union[str, Path]):
    # TODO: This seems to be broken, unsure it even works
    if isinstance(path, str):
        path_str = path
    elif isinstance(path, Path):
        path_str = str(path)
    else:
        print('Wrong type!')
        return None

    try:
        # Get file stats
        stat_info = os.stat(path_str)

        # Check the number of hard links
        if stat_info.st_nlink > 1:
            return True
        else:
            return False
    except FileNotFoundError:
        print(f"File not found: {path_str}")
        return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False


def is_junction(path: Union[str, Path]):
    if get_os() == OS.WIN:
        return junctionUtils.is_junction(path)
    else:
        return False


def is_symbolic_link(path: Union[str, Path]):
    if os.path.islink(path):
        return True
    else:
        return False


def is_mount(path: Union[str, Path]):
    if os.path.ismount(path):
        return True
    else:
        return False


def is_mount_point(path: Union[str, Path]):
    if get_os() != OS.WIN:
        return False

    # Convert type
    if isinstance(path, str):
        path_str = path
    elif isinstance(path, Path):
        path_str = str(path)
    else:
        print('Wrong type!')
        return None

    # FSUTIL QUERY
    output_lines = cmdShellWrapper.exec_cmd(f'fsutil reparsepoint query "{path_str}"')
    for line in output_lines:
        if line == 'Tag value: Mount Point':
            return True
    return False


def is_dir(path: Union[str, Path]):
    """
    Returns whether a path is a directory.
    More accurate than os.path.isdir as it will return False if the target is a junction, symbolic link or hard link
    """

    if not os.path.isdir(path):
        return False
    # elif is_hard_link(path):
    #     return False
    elif is_junction(path):
        return False
    elif is_mount_point(path):
        return False
    elif is_symbolic_link(path):
        return False
    else:
        return True


def get_split_character():
    match get_os():
        case OS.WIN:
            return '\\'
        case OS.MAC | OS.LINUX:
            return '/'


def open_dir_path(dir_path):
    """
    Opens the directory path that is given as a string
    :param dir_path: Directory to open
    :type dir_path: str
    """
    if os.path.isdir(dir_path):  # Validate string is in fact a path
        if sys.platform == "win32":
            os.startfile(dir_path)
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.call([opener, dir_path])
    else:
        print('ERROR: UNABLE TO OPEN PROJECT DIRECTORY.'
              '\nAttempted path: ' + dir_path)


def write_file(file_path: Union[str, Path], write_str: Union[str, List[str]]):
    """
    Creates a file (if not created yet) and writes to it
    :param file_path: Path to write to
    :type file_path: Union[Path, str]
    :param write_str: String to write (or List of strings)
    :type write_str: str
    """
    # Get folder in which the file is
    file_dir = Path(file_path).parent

    # Create directory to store file in, if not created yet
    Path(file_dir).mkdir(parents=True, exist_ok=True)

    # Write to the file
    f = open(file_path, 'w+')
    if isinstance(write_str, str):
        f.write(write_str)
    elif isinstance(write_str, List):
        f.writelines(write_str)
    f.close()

    # If macOS, ensure can be run
    if not sys.platform == 'win32':
        subprocess.check_call(['chmod', '+x', file_path])


def search_replace_xml(xml_file_path, search_str, replace_str):
    """
    Search and replace in designated xml file. Overwrites file with results.
    :param xml_file_path: Path of XML file (must incl. ext.)
    :type xml_file_path: str
    :param search_str: String to search for
    :type search_str: str
    :param replace_str: String to replace with
    :type replace_str: str
    """

    new_line_lst = []
    reading_file = open(xml_file_path, "r")
    content = reading_file.read()
    for line in content.splitlines():  # or whatever arbitrary loop
        line_decoded = line
        line_replaced = line_decoded.replace(search_str, replace_str)
        new_line_lst.append(line_replaced)

    print('THIS FILE HAS LINES: ' + str(len(new_line_lst)))
    reading_file = open(xml_file_path, 'w')

    current_line_count = 0
    for line in new_line_lst:
        current_line_count += 1

        if current_line_count < len(new_line_lst):
            reading_file.write(line + '\n')
        else:
            reading_file.write(line)

    reading_file.close()


def write_file_append(file_path, write_str):
    """
    Appends text on an additional line in an existing text file
    """
    with open(file_path, 'a') as f:
        f.write('\n' + str(write_str))


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
        if sys.platform == 'win32' and force and new_name.exists():
            delete_file(new_name)

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


def copy_file(source, destination):
    """
    Copies file from source to destination.
    """
    # If destination directory does not exist, create
    destination_dir = os.path.dirname(destination)
    make_dir(destination_dir)

    # Copy file
    log(Severity.DEBUG, 'fileUtils.copy_file', f'Copying file from "{source}" to "{destination}"')
    copyfile(source, destination)


def make_dir(directory):
    """
    Creates directory at location (if it doesn't exist)
    """
    if not os.path.exists(directory):
        log(Severity.DEBUG, 'fileUtils.make_dir', f'Creating Directory at "{directory}"')
        Path(directory).mkdir(parents=True, exist_ok=True)


def is_dir_empty(path: Path) -> bool:
    return not any(path.iterdir())


def get_current_working_dir() -> Path:
    current_file = os.path.abspath(__file__)
    cwd = Path(current_file).parent.parent
    cwd_resolved = Path.resolve(cwd)
    return cwd_resolved

def get_project_temp_dir() -> Path:
    cwd = get_current_working_dir()
    temp_dir_path = Path(Path(cwd).parent, 'temp')
    return temp_dir_path

def get_user_home_dir() -> Path:
    """
    Get the current user's home directory
    """
    return Path.home()


def get_user_documents_dir() -> Path:
    """
    Gets the current user's documents directory
    """
    op_sys = get_os()
    match op_sys:
        case OS.MAC:
            return Path(get_user_home_dir(), 'Documents')
        case _:
            print(f'Platform not suppported for get_user_documents_dir as of yet!')
            return None


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


def is_file(path: Path) -> bool:
    if os.path.isfile(path):
        return True
    else:
        return False


def get_permission(path: Path):
    """
    For macOS, gets permission of a file. Helpful if a file won't run or open
    """
    tool_name = 'MacOS Permission'
    # App Run permissions
    log(Severity.DEBUG, tool_name, f'Getting CHMOD+X Permission for "{path}"')
    cmdShellWrapper.exec_cmd(f'chmod +x "{path}"')


def ensure_file_writable_if_exists(file_path: str | Path) -> bool:
    """
    Ensures the file is writable by the owner, without removing any
    existing permissions.

    Returns False if the file does not exist.
    Raises PermissionError / OSError on failure.
    """
    p = Path(file_path)

    if not p.exists() or not p.is_file():
        return False

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

