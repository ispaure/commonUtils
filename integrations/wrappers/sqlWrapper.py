"""Compatibility helpers that return complete SQLite results in memory."""

from contextlib import closing
from pathlib import Path
import sqlite3

from ..sqlite.model import _quote


def exec_sql_command(db_file, sql_cmd):
    """Execute and commit one trusted caller-supplied statement; return all result tuples."""
    with closing(sqlite3.connect(db_file)) as connection, connection:
        with closing(connection.execute(sql_cmd)) as cursor:
            return cursor.fetchall()


def fetch_sql_table(db_file, table_name, column_lst=None):
    """Read a whole table or view into numbered dictionaries; use Database.page for bounds."""
    uri = Path(db_file).absolute().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        entry = connection.execute(
            "SELECT name FROM main.sqlite_schema "
            "WHERE name = ? COLLATE NOCASE AND type IN ('table', 'view') "
            "UNION ALL SELECT ? WHERE ? IN ('sqlite_master', 'sqlite_schema') COLLATE NOCASE",
            (table_name, table_name, table_name),
        ).fetchone()
        if entry is None:
            raise sqlite3.OperationalError(f'Unknown SQLite table {table_name!r}.')
        table = 'main.' + _quote(entry[0])
        if column_lst is None:
            selected = '*'
        else:
            names = tuple(column_lst)
            if not names or any(not isinstance(name, str) for name in names):
                raise sqlite3.OperationalError('Select existing SQLite columns.')
            for name in names:
                if connection.execute(
                    'SELECT 1 FROM pragma_table_xinfo(?, ?) WHERE name = ? COLLATE NOCASE',
                    (entry[0], 'main', name),
                ).fetchone() is None:
                    raise sqlite3.OperationalError(f'Unknown SQLite column {name!r}.')
            selected = ', '.join(map(_quote, names))
        with closing(connection.execute(f'SELECT {selected} FROM {table}')) as cursor:
            if column_lst is None:
                names = tuple(column[0] for column in cursor.description)
            return [
                dict(row_number=index) | dict(zip(names, values))
                for index, values in enumerate(cursor, start=1)
            ]
