"""Schema and declared-key introspection for SQLite resources."""

from dataclasses import dataclass
from hashlib import sha256
import sqlite3

from .model import Column, Table, ValidationError, _quote


@dataclass(frozen=True)
class _Key:
    name: str
    collation: str | None = None
    descending: bool = False

    @property
    def expression(self) -> str:
        column = _quote(self.name)
        if self.collation is not None:
            return f'{column} COLLATE {_quote(self.collation)}'
        return column


@dataclass(frozen=True)
class _TableSchema:
    table: Table
    keys: tuple[_Key, ...]
    rowid: str | None
    order_by_values: bool

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.table.columns)


def _qualified(name: str) -> str:
    return 'main.' + _quote(name)


def _catalog(connection: sqlite3.Connection, name: str | None = None) -> list[tuple]:
    sql = ('SELECT name, type, wr FROM pragma_table_list '
           "WHERE schema = 'main' AND name != 'sqlite_schema'")
    if name is None:
        return connection.execute(sql + ' ORDER BY name COLLATE BINARY').fetchall()
    return connection.execute(sql + ' AND name = ? COLLATE BINARY', (name,)).fetchall()


def _inspect_table(
    connection: sqlite3.Connection, entry: tuple[str, str, int],
    file_identity: tuple[int, int], schema_version: int,
) -> _TableSchema:
    name, kind, without_rowid = entry
    columns = tuple(Column(name, declared, bool(required), default, pk, hidden)
                    for name, declared, required, default, pk, hidden in connection.execute(
                        'SELECT name, type, "notnull", dflt_value, pk, hidden '
                        "FROM pragma_table_xinfo(?, 'main') ORDER BY cid", (name,)))
    primary_columns = sorted((column for column in columns if column.pk_order),
                             key=lambda column: column.pk_order)
    primary_key = tuple(column.name for column in primary_columns)
    keys = tuple(_Key(column) for column in primary_key)
    primary_index = None
    if kind == 'table' and primary_key:
        primary_index = connection.execute(
            "SELECT name FROM pragma_index_list(?, 'main') WHERE origin = 'pk'", (name,)
        ).fetchone()
        if primary_index:
            keys = tuple(_Key(column, collation, bool(descending))
                         for column, collation, descending in connection.execute(
                             'SELECT name, coll, "desc" '
                             "FROM pragma_index_xinfo(?, 'main') WHERE key ORDER BY seqno",
                             primary_index))
    if kind != 'table':
        reason = f'SQLite {kind} objects are read-only.'
    elif name.lower().startswith('sqlite_'):
        reason = 'SQLite system tables are read-only.'
    elif not keys:
        reason = 'This table has no declared primary key.'
    else:
        reason = None

    rowid = None
    needs_tiebreaker = not keys or (primary_index and any(
        not column.not_null for column in primary_columns))
    if kind in ('table', 'shadow') and not without_rowid and needs_tiebreaker:
        names_lower = {column.name.lower() for column in columns}
        rowid = next((alias for alias in ('rowid', '_rowid_', 'oid')
                      if alias not in names_lower), None)

    objects = tuple(connection.execute(
        'SELECT type, name, rootpage, sql FROM main.sqlite_schema '
        'WHERE tbl_name = ? COLLATE BINARY ORDER BY type, name', (name,)))
    token_data = (file_identity, schema_version, entry, columns, keys, objects)
    schema_token = sha256(repr(token_data).encode('utf-8')).hexdigest()
    table = Table(name, kind, columns, primary_key, schema_token, reason is None, reason)
    return _TableSchema(table, keys, rowid, bool(needs_tiebreaker and rowid is None))


def _name(value: str | Table) -> str:
    name = value.name if isinstance(value, Table) else value
    if not isinstance(name, str) or '\x00' in name:
        raise ValidationError('Use the SQLite table name reported by tables().')
    return name
