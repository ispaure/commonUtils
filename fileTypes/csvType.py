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
import csv
from ..fileUtils import File


# ----------------------------------------------------------------------------------------------------------------------
# CODE

class CSVFile(File):
    def __init__(self, path: Path):
        super().__init__(path)

    def read_csv(self) -> List[List[str]]:
        """
        Reads the CSV file and returns its contents as a list of rows,
        where each row is a list of cell values.
        """
        csv_data: List[List[str]] = []

        with open(self.path, 'r', encoding='utf-8-sig', newline='') as file:
            reader = csv.reader(file)

            for row in reader:
                csv_data.append(row)

        return csv_data

    def write_csv(self, csv_data: List[List[str]]):
        """
        Writes a list of rows to the CSV file using standard CSV formatting.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.make_writable()

        with open(self.path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.writer(file)

            for row in csv_data:
                writer.writerow(row)
