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

from typing import List

# Common utilities
from . import logUtils
from .fileTypes import csvType


class Cell:
    def __init__(self, txt: str):
        self.txt = txt


class Row:
    def __init__(self):
        self.__cell_lst: List[Cell] = []

    def append_cell(self, cell: Cell):
        self.__cell_lst.append(cell)

    def get_cell(self, idx):
        if idx + 1 > len(self.__cell_lst):
            msg = 'Index out of range in cells: '
            cell_txt_lst = []

            for cell in self.__cell_lst:
                cell_txt_lst.append(cell.txt)

            msg += ', '.join(cell_txt_lst)
            logUtils.log_msg(msg)
        else:
            return self.__cell_lst[idx]

    def get_cells(self):
        return self.__cell_lst


class Spreadsheet:
    def __init__(self, name: str):
        self.name = name
        self.__row_lst: List[Row] = []

    def append_row(self, row: Row):
        self.__row_lst.append(row)

    def get_rows(self):
        return self.__row_lst

    def export_file(self, file: csvType.CSVFile):
        logUtils.log_msg(f'Exporting Spreadsheet to {file.path}')

        csv_data: List[List[str]] = []

        for row in self.__row_lst:
            csv_row = [
                cell.txt
                for cell in row.get_cells()
            ]

            csv_data.append(csv_row)

        file.write_csv(csv_data)

    def import_file(self, file: csvType.CSVFile):
        logUtils.log_msg(f'Importing spreadsheet from {file.path}')

        if not file.path.exists():
            return

        csv_data = file.read_csv()

        for csv_row in csv_data:
            row = Row()

            for cell_txt in csv_row:
                row.append_cell(Cell(cell_txt))

            self.append_row(row)
