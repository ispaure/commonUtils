# String tables

Import from `commonUtils.formats.tables`. Implementation and public exports live in
[`tables.py`](../../../formats/tables.py).

Public entry points: `Cell`, `Row`, `Spreadsheet`

[Library overview](../../overview.md).

This small API represents rows of string cells and CSV import/export; it does not evaluate formulas or implement a workbook. Imports append rows, preserving existing callers. Missing input files leave the table unchanged.
