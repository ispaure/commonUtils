"""CSV table consumer behavior survives the explicit string-table owner."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.formats.csvType import CSVFile
from commonUtils.formats.tables import Cell, Row, Spreadsheet


class StringTableTests(unittest.TestCase):
    def test_roundtrip_quotes_unicode_empty_cells_and_append_import(self):
        with TemporaryDirectory() as temporary:
            file = CSVFile(Path(temporary) / 'table.csv')
            table = Spreadsheet('fixture')
            row = Row()
            for value in ('é', 'a,b', '', '"quoted"'):
                row.append_cell(Cell(value))
            table.append_row(row)
            table.export_file(file)
            restored = Spreadsheet('restored')
            restored.import_file(file)
            self.assertEqual([cell.txt for cell in restored.get_rows()[0].get_cells()], ['é', 'a,b', '', '"quoted"'])
            restored.import_file(file)
            self.assertEqual(len(restored.get_rows()), 2)
            restored.import_file(CSVFile(Path(temporary) / 'missing.csv'))
            self.assertEqual(len(restored.get_rows()), 2)
