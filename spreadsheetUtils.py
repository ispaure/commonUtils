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
import os

# Common utilities
from . import fileUtils, logUtils


class Cell:
    def __init__(self, txt: str):
        self.txt = txt

    def get_csv_cell(self):
        return self.txt.replace(',', '<comma>')


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

    def get_csv_line(self):
        cell_str_lst = []
        for cell in self.__cell_lst:
            cell_str_lst.append(cell.get_csv_cell())
        return ','.join(cell_str_lst) + '\n'


class Spreadsheet:
    def __init__(self, name: str):
        self.__row_lst: List[Row] = []

    def append_row(self, row: Row):
        self.__row_lst.append(row)

    def get_rows(self):
        return self.__row_lst

    def export_file(self, path: Path):
        logUtils.log_msg(f'Exporting Spreadsheet to {path}')
        csv_output_str: str = ''

        for row in self.__row_lst:
            csv_output_str += row.get_csv_line

        if csv_output_str.endswith('\n'):
            csv_output_str = csv_output_str.rstrip('\n')

        if not os.path.isdir(path.parent):
            fileUtils.make_dir(path.parent)

        with open(str(path), 'w') as out:
            out.write(csv_output_str)

    def import_file(self, path: Union[str, Path]):
        logUtils.log_msg(f'Importing spreadsheet from {path}')
        if isinstance(path, str):
            path = Path(path)

        if path.exists():
            with open(path, 'r') as input:
                line_lst = input.readlines()
            for line in line_lst:
                cell_lst = line.split(',')
                row = Row()
                for cell in cell_lst:
                    row.append_cell(Cell(cell.replace('\n', '')))
                self.append_row(row)
