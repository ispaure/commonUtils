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
import zipfile
from .archiveType import ArchiveFile
from ..debugUtils import *


class ZIPFile(ArchiveFile):
    def __init__(self, path: Path):
        # Call the parent (File) initializer
        super().__init__(path)

    def extract(self, dest_path: Path, show_progress: bool = False, *, password=None) -> bool:
        """Extract the ZIP File"""
        from ..zipUtils import unzip_file
        return unzip_file(self.path, dest_path, pwd=password, show_progress=show_progress)

    def open_archive(self, *, password=None):
        """Open for reading with an explicit password; no prompts or configuration."""
        from ..zip_access import open_archive
        return open_archive(self.path, password=password)

    def is_encrypted(self) -> bool:
        from ..zip_access import is_encrypted
        return is_encrypted(self.path)

    def get_root_file_lst(self) -> List[str]:
        try:
            with zipfile.ZipFile(self.path, 'r') as zip_ref:
                # list of all entries at root (no '/')
                return [Path(f).name for f in zip_ref.namelist() if '/' not in f]
        except zipfile.BadZipFile:
            log(Severity.CRITICAL, "CBZFile", f"Invalid ZIP structure in {self.path}")


from .registry import register_file_type
register_file_type(ZIPFile, 'zip', priority=-100)
