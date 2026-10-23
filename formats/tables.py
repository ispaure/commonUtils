"""Small string tables backed by CSV, retaining the Cell/Row/Spreadsheet API."""
from dataclasses import dataclass
from ..runtime.diagnostics import log, Severity
from . import csvType


@dataclass
class Cell:
    txt: str


class Row:
    def __init__(self):
        self.__cell_lst: list[Cell] = []

    def append_cell(self, cell: Cell):
        self.__cell_lst.append(cell)

    def get_cell(self, idx):
        if idx + 1 > len(self.__cell_lst):
            msg = 'Index out of range in cells: '
            cell_txt_lst = []

            for cell in self.__cell_lst:
                cell_txt_lst.append(cell.txt)

            msg += ', '.join(cell_txt_lst)
            log(Severity.WARNING, 'Table', msg)
        else:
            return self.__cell_lst[idx]

    def get_cells(self):
        return self.__cell_lst


class Spreadsheet:
    def __init__(self, name: str):
        self.name = name
        self.__row_lst: list[Row] = []

    def append_row(self, row: Row):
        self.__row_lst.append(row)

    def get_rows(self):
        return self.__row_lst

    def export_file(self, file: csvType.CSVFile):
        log(Severity.INFO, 'Table', f'Exporting Spreadsheet to {file.path}')

        file.write_csv([[cell.txt for cell in row.get_cells()] for row in self.__row_lst])

    def import_file(self, file: csvType.CSVFile):
        log(Severity.INFO, 'Table', f'Importing spreadsheet from {file.path}')

        if not file.path.exists():
            return

        csv_data = file.read_csv()

        for csv_row in csv_data:
            row = Row()
            for cell_txt in csv_row:
                row.append_cell(Cell(cell_txt))
            self.append_row(row)
