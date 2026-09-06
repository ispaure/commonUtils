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
from . import fileUtils
import os, subprocess, sys
from shutil import rmtree
from typing import List, Optional, Union
import stat


class Directory:
    def __init__(self, path: Path):
        if not isinstance(path, Path):
            log(Severity.CRITICAL, 'Directory.__init__', f'Expected Path when creating {type(self).__name__}, got {type(path).__name__}: {path!r}')
            raise TypeError(f'{type(self).__name__} path must be a pathlib.Path, got {type(path).__name__}')

        self.path: Path = path
        self.name = self.__get_dir_name()

    def __get_dir_name(self):
        return self.path.name

    def open(self):
        path_str = str(self.path)

        if os.path.isdir(path_str):  # Validate string is in fact a path
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
        Keeps the same ordering/behavior as deprecated get_file_list_from_path.
        """
        list_of_entries = sorted(os.listdir(self.path))
        all_files: List[fileUtils.File] = []

        for entry in list_of_entries:
            full_path = self.path / entry

            if full_path.is_dir():
                if recursive:
                    all_files += Directory(full_path).list_files(recursive=recursive, filter_extension=filter_extension)
            elif full_path.suffix.lower() == '.txt':
                all_files.append(fileUtils.TXTFile(full_path))
            else:
                all_files.append(fileUtils.File(full_path))

        # Apply file extension filter
        if filter_extension is not None:
            if isinstance(filter_extension, str):
                filter_extension = [filter_extension]

            extensions = [ext.lower().lstrip('.') for ext in filter_extension]
            return [file for file in all_files if file.ext in extensions]

        return all_files

    def delete(self) -> bool:
        """
        Deletes the directory on disk.
        """
        if fileUtils.delete_debug_prompt:
            log(Severity.WARNING, 'Directory.delete', f'Deleting "{self.path}", proceed?', popup=True)
        else:
            log(Severity.DEBUG, 'Directory.delete', f'Deleting directory: "{self.path}"')

        rmtree(self.path)
        return not self.path.is_dir()

    def delete_contents(self):
        """
        Deletes the files and folders within the directory, but not the directory itself.
        """
        # Make sure everything is not marked as non-writable
        for root, dirs, files in os.walk(self.path):
            for fname in files:
                os.chmod(Path(root, fname), stat.S_IWRITE)

        # Delete subdirectories
        subdirectories = [Directory(path) for path in self.path.iterdir() if path.is_dir()]
        for directory in subdirectories:
            directory.delete()

        if any(path.is_dir() for path in self.path.iterdir()):
            log(Severity.CRITICAL, 'Directory.delete_contents', 'Could not delete every directory!')

        # Delete remaining files
        rem_file_lst: List[fileUtils.File] = self.list_files(recursive=False)
        for file in rem_file_lst:
            file.delete_file()

        if len(self.list_files(recursive=False)) > 0:
            log(Severity.CRITICAL, 'Directory.delete_contents', 'Could not delete every file!')

    def list_directories(self) -> List['Directory']:
        """
        Returns a sorted list of Directory objects within this directory.
        """
        dir_lst: List[Directory] = []

        for item in os.listdir(self.path):
            item_path = self.path / item

            if item_path.is_dir():
                dir_lst.append(Directory(item_path))

        dir_lst.sort(key=lambda directory: directory.name.lower())
        return dir_lst
