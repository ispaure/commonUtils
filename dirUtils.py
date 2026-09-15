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

from pathlib import Path
from .debugUtils import *
from . import fileUtils, linkUtils
from .fileTypes import txtType, csvType
import os, subprocess, sys
from typing import List, Optional, Set, Union


class Directory:
    def __init__(self, path: Path):
        if not isinstance(path, Path):
            log(Severity.CRITICAL, 'Directory.__init__', f'Expected Path when creating {type(self).__name__}, got {type(path).__name__}: {path!r}')
            raise TypeError(f'{type(self).__name__} path must be a pathlib.Path, got {type(path).__name__}')

        self.path: Path = path
        self.name = self.__get_dir_name()

    def __get_dir_name(self):
        return self.path.name

    @staticmethod
    def __get_file_from_path(path: Path) -> fileUtils.File:
        if path.suffix.lower() == '.txt':
            return txtType.TXTFile(path)
        elif path.suffix.lower() == '.csv':
            return csvType.CSVFile(path)
        else:
            return fileUtils.File(path)

    @staticmethod
    def __delete_junction(path: Path):
        """
        Deletes a junction without deleting the directory it points to.
        """
        if not path.is_junction():
            log(Severity.CRITICAL, 'Directory.__delete_junction', f'Path is not a junction: "{path}"')

        try:
            path.rmdir()
        except Exception as e:
            log(Severity.CRITICAL, 'Directory.__delete_junction', f'Could not delete junction "{path}"\n{type(e).__name__}: {e}')

        if path.exists() or path.is_junction():
            log(Severity.CRITICAL, 'Directory.__delete_junction', f'Junction still exists after deletion attempt: "{path}"')

    def open(self):
        path_str = str(self.path)

        if self.is_dir():  # Symbolic links and junctions resolving to directories are valid
            if sys.platform == "win32":
                os.startfile(path_str)
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.call([opener, path_str])
        else:
            log(Severity.ERROR, 'Directory.open', f'Unable to open directory "{self.path}"')

    def list_files(self, recursive: bool = True, filter_extension: Optional[Union[str, List[str]]] = None) -> List[fileUtils.File]:
        """
        Returns a list of File objects under this directory.
        Uses the appropriate File subclass based on the file extension.
        Follows symbolic links and junctions to directories, but raises a CRITICAL error if recursive traversal is detected.
        Keeps the same ordering/behavior as deprecated get_file_list_from_path.
        """
        ancestor_paths: Set[Path] = {self.path.resolve()}
        all_files = self.__list_files(recursive=recursive, ancestor_paths=ancestor_paths)

        # Apply file extension filter
        if filter_extension is not None:
            if isinstance(filter_extension, str):
                filter_extension = [filter_extension]

            extensions = [ext.lower().lstrip('.') for ext in filter_extension]
            return [file for file in all_files if file.ext in extensions]

        return all_files

    def __list_files(self, recursive: bool, ancestor_paths: Set[Path]) -> List[fileUtils.File]:
        all_files: List[fileUtils.File] = []

        for full_path in sorted(self.path.iterdir(), key=lambda path: path.name):
            if full_path.is_dir():
                if recursive:
                    resolved_path = full_path.resolve()

                    if resolved_path in ancestor_paths:
                        log(Severity.CRITICAL, 'Directory.list_files', f'Recursive directory link detected at "{full_path}" resolving to "{resolved_path}"')

                    child_ancestor_paths = ancestor_paths | {resolved_path}
                    all_files += Directory(full_path).__list_files(recursive=True, ancestor_paths=child_ancestor_paths)
            else:
                all_files.append(self.__get_file_from_path(full_path))

        return all_files

    def delete(self, make_writable: bool = False) -> bool:
        """
        Deletes this directory from disk.

        If this Directory represents a symbolic link or junction, only the link itself is deleted.
        The directory it points to is never deleted.

        By default, file permissions are not modified during deletion.
        If make_writable is True, files that cannot be deleted due to permissions may be made writable and retried.
        """
        if fileUtils.delete_debug_prompt:
            log(Severity.WARNING, 'Directory.delete', f'Deleting "{self.path}", proceed?', popup=True)
        else:
            log(Severity.DEBUG, 'Directory.delete', f'Deleting directory: "{self.path}"')

        # Delete symbolic links without touching their targets
        if self.path.is_symlink():
            linkUtils.delete_symbolic_link(self.path)
            return True

        # Delete junctions without touching their targets
        if self.path.is_junction():
            self.__delete_junction(self.path)
            return True

        # Delete contents first, then the directory itself
        self.delete_contents(make_writable=make_writable)

        try:
            self.path.rmdir()
        except Exception as e:
            log(Severity.CRITICAL, 'Directory.delete', f'Could not delete directory "{self.path}"\n{type(e).__name__}: {e}')

        if self.path.exists():
            log(Severity.CRITICAL, 'Directory.delete', f'Directory still exists after deletion attempt: "{self.path}"')

        return True

    def delete_contents(self, follow_root_link: bool = False, make_writable: bool = False):
        """
        Deletes the files and folders within the directory, but not the directory itself.

        Symbolic links and junctions found inside the directory are deleted without deleting their targets.
        If this Directory itself is a symbolic link or junction, deletion is refused with a CRITICAL error unless
        follow_root_link is True.

        By default, file permissions are not modified during deletion.
        If make_writable is True, files that cannot be deleted due to permissions may be made writable and retried.
        """
        # Do not follow a linked root for destructive operations unless explicitly requested
        if self.path.is_symlink() or self.path.is_junction():
            if not follow_root_link:
                log(Severity.CRITICAL, 'Directory.delete_contents', f'Unable to delete contents of linked directory "{self.path}" without follow_root_link=True')

            resolved_path = self.path.resolve()
            Directory(resolved_path).delete_contents(make_writable=make_writable)
            return

        # Delete directory contents
        for path in list(self.path.iterdir()):
            # Delete symbolic links without touching their targets
            if path.is_symlink():
                linkUtils.delete_symbolic_link(path)

            # Delete junctions without touching their targets
            elif path.is_junction():
                self.__delete_junction(path)

            # Delete real subdirectories recursively
            elif path.is_dir():
                Directory(path).delete(make_writable=make_writable)

            # Delete files
            else:
                file = self.__get_file_from_path(path)
                file.delete_file(make_writable=make_writable)

        if any(self.path.iterdir()):
            log(Severity.CRITICAL, 'Directory.delete_contents', f'Could not delete every item from directory "{self.path}"')

    def list_directories(self) -> List['Directory']:
        """
        Returns a sorted list of Directory objects within this directory.

        Symbolic links and junctions resolving to directories are included as Directory objects.
        """
        dir_lst: List[Directory] = []

        for item_path in self.path.iterdir():
            if item_path.is_dir():
                dir_lst.append(Directory(item_path))

        dir_lst.sort(key=lambda directory: directory.name.lower())
        return dir_lst

    def is_dir(self) -> bool:
        """
        Returns True if this path resolves to a directory.

        Symbolic links and junctions pointing to directories are considered directories.
        """
        return self.path.is_dir()

    def is_dir_empty(self) -> bool:
        return not any(self.path.iterdir())

    def make_dir(self):
        """
        Creates directory at location (if it doesn't exist)
        """
        if not self.is_dir():
            log(Severity.DEBUG, 'Directory.make_dir', f'Creating directory at location "{self.path}"')
            self.path.mkdir(parents=True, exist_ok=True)
