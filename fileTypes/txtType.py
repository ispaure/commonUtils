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
import subprocess
from pathlib import Path
from ..osUtils import *
from ..fileUtils import File
from ..debugUtils import *


# ----------------------------------------------------------------------------------------------------------------------
# CODE


class TXTFile(File):
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
