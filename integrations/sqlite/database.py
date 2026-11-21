"""Bounded reads and transactional writes against an existing SQLite file."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
import os
from pathlib import Path
import sqlite3
import stat
from types import TracebackType

from .model import (
    BusyError, CancelledError, ConstraintError, Page, Predicate, ReadOnlyError,
    Row, RowToken, Sort, SQLiteError, StaleDataError, Table, ValidationError, Value,
    _bind_value, _column, _compile_filter, _quote,
)
from .schema import _TableSchema, _catalog, _inspect_table, _name, _qualified


def _database_error(error: sqlite3.Error) -> SQLiteError:
    code = getattr(error, 'sqlite_errorcode', 0)
    primary_code = code & 0xff
    if code == sqlite3.SQLITE_READONLY_DBMOVED:
        return StaleDataError('The SQLite database file moved. Reopen it before saving.')
    if primary_code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        return BusyError(f'The SQLite database is locked. Retry after other writers finish. {error}')
    if primary_code in (sqlite3.SQLITE_READONLY, sqlite3.SQLITE_PERM, sqlite3.SQLITE_AUTH):
        return ReadOnlyError(f'SQLite denied access. {error}')
    if primary_code == sqlite3.SQLITE_SCHEMA:
        return StaleDataError('The SQLite schema changed. Reload before saving.')
    if primary_code == sqlite3.SQLITE_CONSTRAINT:
        return ConstraintError(str(error))
    if primary_code == sqlite3.SQLITE_INTERRUPT:
        return CancelledError('The SQLite operation was cancelled.')
    if isinstance(error, (sqlite3.ProgrammingError, sqlite3.InterfaceError)):
        return ValidationError(str(error))
    return SQLiteError(str(error))


def _file_identity(path: Path, *, writable: bool = False) -> tuple[int, int]:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValidationError('Open an existing SQLite database file.')
    if writable:
        write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
        if not (info.st_mode & write_bits) or not os.access(path, os.W_OK):
            raise ReadOnlyError('The SQLite file is read-only. Use a writable copy to save edits.')
    return info.st_dev, info.st_ino


def _page_bounds(limit: int, offset: int = 0) -> None:
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValidationError('SQLite page size must be between 1 and 1000 rows.')
    if type(offset) is not int or not 0 <= offset < 2 ** 63:
        raise ValidationError('SQLite page offset must be a nonnegative signed 64-bit integer.')


def _read_authorizer(action: int, _arg1: str | None, arg2: str | None,
                     _database: str | None, _source: str | None) -> int:
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and arg2 and arg2.lower() != 'load_extension':
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class Database:
    """Context-managed access to an existing local SQLite database."""

    def __init__(
        self, path: str | os.PathLike[str], writable: bool = False, timeout: float = 0.25,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        try:
            self.path = Path(path).absolute()
        except (TypeError, ValueError, OSError) as error:
            raise ValidationError('Use a local SQLite database file path.') from error
        if type(writable) is not bool:
            raise ValidationError('Set writable explicitly to True or False.')
        if type(timeout) not in (int, float) or not 0 <= timeout <= 2_147_483:
            raise ValidationError('SQLite lock timeout must be a nonnegative finite number of seconds.')
        if cancelled is not None and not callable(cancelled):
            raise ValidationError('Supply a callable to check cancellation.')
        self._writable = writable
        self._timeout = timeout
        self._cancelled = cancelled
        self._connection: sqlite3.Connection | None = None
        self._identity: tuple[int, int] | None = None
        self._active_transaction: Transaction | None = None
        self._callback_error: BaseException | None = None

    def __enter__(self) -> 'Database':
        if self._connection is not None:
            raise ValidationError('This SQLite database is already open.')
        if sqlite3.sqlite_version_info < (3, 37, 0):
            raise SQLiteError('SQLite 3.37 or newer is required to inspect database objects safely.')
        self._check_cancelled()
        try:
            identity = _file_identity(self.path, writable=self._writable)
        except (OSError, ValueError) as error:
            raise SQLiteError(f'Cannot open SQLite file {self.path}: {error}') from error
        mode = 'rw' if self._writable else 'ro'
        with self._sqlite_errors():
            self._connection = sqlite3.connect(
                f'{self.path.as_uri()}?mode={mode}', uri=True, timeout=self._timeout,
                isolation_level=None, cached_statements=0,
            )
            self._identity = identity
            try:
                self._check_file()
                connection = self._connection
                connection.execute('PRAGMA trusted_schema = OFF')
                connection.execute('PRAGMA foreign_keys = ON')
                if connection.execute('PRAGMA foreign_keys').fetchone() != (1,):
                    raise SQLiteError('This SQLite runtime cannot enforce foreign keys.')
                if hasattr(connection, 'setconfig') and hasattr(sqlite3, 'SQLITE_DBCONFIG_DEFENSIVE'):
                    connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
                self._restore_progress(connection)
                connection.execute('PRAGMA main.schema_version').fetchone()
                self._check_cancelled()
            except BaseException:
                self.close()
                raise
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _opened(self) -> sqlite3.Connection:
        if self._connection is None:
            raise ValidationError('Open the SQLite database with a with block first.')
        return self._connection

    def close(self) -> None:
        """Close the connection, rolling back any active transaction."""
        if self._connection is None:
            return
        connection = self._connection
        self._connection = None
        self._identity = None
        with self._sqlite_errors():
            try:
                connection.set_progress_handler(None, 0)
                if connection.in_transaction:
                    connection.execute('ROLLBACK')
            finally:
                connection.close()

    def _check_cancelled(self) -> None:
        if self._cancelled is not None and self._cancelled():
            raise CancelledError('The SQLite operation was cancelled.')

    def _progress(self) -> int:
        try:
            return int(bool(self._cancelled()))
        except BaseException as error:
            self._callback_error = error
            return 1

    def _restore_progress(self, connection: sqlite3.Connection) -> None:
        if self._cancelled is not None:
            connection.set_progress_handler(self._progress, 1000)

    @contextmanager
    def _sqlite_errors(self) -> Iterator[None]:
        try:
            yield
        except sqlite3.Error as error:
            callback_error = self._callback_error
            self._callback_error = None
            if callback_error is not None:
                raise callback_error from error
            raise _database_error(error) from error

    def _check_file(self) -> None:
        try:
            identity = _file_identity(self.path, writable=self._writable)
        except (OSError, ValidationError) as error:
            raise StaleDataError('The SQLite database file is unavailable. Reopen it before continuing.') from error
        if identity != self._identity:
            raise StaleDataError('The SQLite database file was replaced. Reopen it before continuing.')

    def _rollback(self, connection: sqlite3.Connection) -> None:
        if not connection.in_transaction:
            return
        connection.set_progress_handler(None, 0)
        try:
            connection.execute('ROLLBACK')
        finally:
            self._restore_progress(connection)

    @contextmanager
    def _read_snapshot(self) -> Iterator[sqlite3.Connection]:
        connection = self._opened()
        self._check_cancelled()
        with self._sqlite_errors():
            if self._active_transaction is not None:
                yield connection
                self._check_cancelled()
                return
            try:
                connection.execute('BEGIN')
                self._check_file()
                yield connection
                self._check_file()
                self._check_cancelled()
            finally:
                self._rollback(connection)

    def _schema(self, connection: sqlite3.Connection, table: str | Table) -> _TableSchema:
        name = _name(table)
        entry = _catalog(connection, name)
        if not entry:
            raise ValidationError(f'Unknown SQLite table {name!r}.')
        version = connection.execute('PRAGMA main.schema_version').fetchone()[0]
        return _inspect_table(connection, entry[0], self._identity, version)

    def tables(self) -> tuple[Table, ...]:
        """Describe tables, views, virtual tables and shadow tables in the main schema."""
        with self._read_snapshot() as connection:
            version = connection.execute('PRAGMA main.schema_version').fetchone()[0]
            return tuple(_inspect_table(connection, entry, self._identity, version).table
                         for entry in _catalog(connection))

    def table(self, name: str) -> Table:
        """Return current metadata for a table by its exact SQLite name."""
        with self._read_snapshot() as connection:
            return self._schema(connection, name).table

    def page(
        self, table: str | Table, columns: Sequence[str] | None = None,
        filters: Predicate | None = None, sort: Sequence[Sort] = (), limit: int = 100,
        offset: int = 0,
    ) -> Page:
        """Read a bounded table page with a one-row lookahead."""
        _page_bounds(limit, offset)
        with self._read_snapshot() as connection:
            schema = self._schema(connection, table)
            if isinstance(table, Table) and schema.table.schema_token != table.schema_token:
                raise StaleDataError('The SQLite table definition changed. Reload its schema.')
            return self._table_page(connection, schema, columns, filters, sort, limit, offset)

    def _table_page(
        self, connection: sqlite3.Connection, schema: _TableSchema,
        columns: Sequence[str] | None, filters: Predicate | None,
        sort: Sequence[Sort], limit: int, offset: int,
    ) -> Page:
        names = schema.names
        visible = tuple(column.name for column in schema.table.columns if column.hidden != 1)
        if columns is None:
            projection = visible
        elif isinstance(columns, Sequence) and not isinstance(columns, (str, bytes)):
            projection = tuple(columns)
        else:
            raise ValidationError('Supply a sequence of SQLite column names.')
        if not projection:
            raise ValidationError('Select at least one SQLite column.')
        selected = tuple(_column(column, names) for column in projection)
        if not isinstance(sort, Sequence) or isinstance(sort, (str, bytes)):
            raise ValidationError('Supply a sequence of SQLite Sort items.')
        ordering = []
        for item in sort:
            if not isinstance(item, Sort) or type(item.descending) is not bool:
                raise ValidationError('Use Sort(column, descending=False) to order SQLite pages.')
            ordering.append(_column(item.column, names) + (' DESC' if item.descending else ' ASC'))
        ordering.extend(key.expression + (' DESC' if key.descending else ' ASC') for key in schema.keys)
        if schema.rowid:
            ordering.append(_quote(schema.rowid))
        if schema.order_by_values:
            ordering.extend(f'{_quote(name)} COLLATE BINARY' for name in visible)
        parameters: list[Value] = []
        where = ''
        if filters is not None:
            try:
                where = ' WHERE ' + _compile_filter(filters, names, parameters)
            except RecursionError as error:
                raise ValidationError('The SQLite filter is nested too deeply.') from error
        order = ' ORDER BY ' + ', '.join(ordering) if ordering else ''
        select = ', '.join(map(_quote, names) if schema.table.editable else selected)
        sql = f'SELECT {select} FROM {_qualified(schema.table.name)}{where}{order} LIMIT ? OFFSET ?'
        with closing(connection.execute(sql, (*parameters, limit + 1, offset))) as cursor:
            data = cursor.fetchmany(limit + 1)
        if schema.table.editable:
            indexes = tuple(names.index(name) for name in projection)
            key_indexes = tuple(names.index(name) for name in schema.table.primary_key)
            rows = tuple(self._editable_row(schema.table, projection, indexes, key_indexes, original)
                         for original in data[:limit])
        else:
            rows = tuple(Row(projection, values) for values in data[:limit])
        return Page(projection, rows, len(data) > limit, offset, limit)

    def _editable_row(
        self, table: Table, projection: tuple[str, ...], indexes: tuple[int, ...],
        key_indexes: tuple[int, ...], original: tuple[Value, ...],
    ) -> Row:
        token = None
        if all(original[index] is not None for index in key_indexes):
            token = RowToken(table.name, table.schema_token, self._identity, original)
        return Row(projection, tuple(original[index] for index in indexes), token)

    def query(
        self, sql: str, parameters: Sequence[Value] | Mapping[str, Value] = (), limit: int = 100,
    ) -> Page:
        """Execute one SQLite-parsed read-only SQL statement and fetch at most limit + 1 rows."""
        _page_bounds(limit)
        if not isinstance(sql, str) or '\x00' in sql:
            raise ValidationError('Enter one SQLite read query.')
        if isinstance(parameters, Mapping):
            if any(not isinstance(name, str) for name in parameters):
                raise ValidationError('SQLite named parameters must use text keys.')
            bound = {name: _bind_value(value) for name, value in parameters.items()}
        elif isinstance(parameters, Sequence) and not isinstance(parameters, (str, bytes, bytearray)):
            bound = tuple(_bind_value(value) for value in parameters)
        else:
            raise ValidationError('Supply SQLite parameters as a sequence or named mapping.')
        with self._read_snapshot() as connection:
            connection.set_authorizer(_read_authorizer)
            try:
                with closing(connection.execute(sql, bound)) as cursor:
                    if cursor.description is None:
                        raise ValidationError('Enter one SQLite read query that returns columns.')
                    columns = tuple(description[0] for description in cursor.description)
                    data = cursor.fetchmany(limit + 1)
            finally:
                connection.set_authorizer(None)
        rows = tuple(Row(columns, values) for values in data[:limit])
        return Page(columns, rows, len(data) > limit, 0, limit)

    @contextmanager
    def transaction(self) -> Iterator['Transaction']:
        """Begin an immediate write transaction and commit only a successful batch."""
        connection = self._opened()
        if not self._writable:
            raise ReadOnlyError('Open the SQLite database with writable=True to save edits.')
        if self._active_transaction is not None:
            raise ValidationError('Nested SQLite write transactions are unavailable.')
        transaction = Transaction(self)
        self._active_transaction = transaction
        try:
            with self._sqlite_errors():
                self._check_cancelled()
                self._check_file()
                connection.execute('BEGIN IMMEDIATE')
                self._check_file()
                yield transaction
                if transaction._failure is not None:
                    raise transaction._failure
                if self._connection is not connection or not connection.in_transaction:
                    raise ValidationError('The SQLite write transaction has already ended.')
                self._check_file()
                self._check_cancelled()
                connection.execute('COMMIT')
        finally:
            self._active_transaction = None
            if self._connection is connection:
                with self._sqlite_errors():
                    self._rollback(connection)


def _same_value(before: Value, after: Value) -> bool:
    if type(before) is not type(after):
        return False
    if isinstance(before, float):
        return before.hex() == after.hex()
    return before == after


class Transaction:
    """Mutation methods available within Database.transaction()."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._failure: BaseException | None = None

    @contextmanager
    def _mutation(self) -> Iterator[sqlite3.Connection]:
        database = self._database
        if database._active_transaction is not self:
            raise ValidationError('Use this SQLite transaction inside its active with block.')
        if self._failure is not None:
            raise ValidationError('The SQLite transaction has a failed mutation and will roll back.') from self._failure
        try:
            with database._sqlite_errors():
                connection = database._opened()
                if not connection.in_transaction:
                    raise ValidationError('The SQLite write transaction has already ended.')
                database._check_cancelled()
                database._check_file()
                yield connection
                database._check_cancelled()
        except BaseException as error:
            self._failure = error
            raise

    def _check_schema(
        self, connection: sqlite3.Connection, table: str | Table, schema_token: str
    ) -> _TableSchema:
        if not isinstance(schema_token, str) or not schema_token:
            raise ValidationError('Supply the table schema_token captured before editing.')
        try:
            schema = self._database._schema(connection, table)
        except ValidationError as error:
            raise StaleDataError('The SQLite table is unavailable. Reload its schema.') from error
        if schema.table.schema_token != schema_token:
            raise StaleDataError('The SQLite file or table definition changed. Reload before saving.')
        if not schema.table.editable:
            raise ReadOnlyError(schema.table.read_only_reason)
        return schema

    def _fields(
        self, schema: _TableSchema, values: Mapping[str, Value]
    ) -> tuple[tuple[str, ...], tuple[Value, ...]]:
        if not isinstance(values, Mapping):
            raise ValidationError('Supply SQLite column values as a mapping.')
        writable = tuple(column.name for column in schema.table.columns if column.hidden == 0)
        names = []
        bound = []
        for name, value in values.items():
            if name in schema.names and name not in writable:
                raise ReadOnlyError(f'SQLite column {name!r} is generated or hidden.')
            names.append(_column(name, writable))
            bound.append(_bind_value(value))
        return tuple(names), tuple(bound)

    def insert(self, table: str | Table, values: Mapping[str, Value], *, schema_token: str) -> None:
        """Insert one row using the declared schema and any defaults for omitted columns."""
        with self._mutation() as connection:
            schema = self._check_schema(connection, table, schema_token)
            columns, bound = self._fields(schema, values)
            sql = f'INSERT OR ABORT INTO {_qualified(schema.table.name)}'
            if columns:
                sql += f" ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
            else:
                sql += ' DEFAULT VALUES'
            self._execute_one(connection, sql, bound)

    def _original_key(
        self, connection: sqlite3.Connection, token: RowToken | None
    ) -> tuple[_TableSchema, str, tuple[Value, ...]]:
        if not isinstance(token, RowToken):
            raise ReadOnlyError('This SQLite row has no editable declared primary key.')
        if token.file_identity != self._database._identity:
            raise StaleDataError('The SQLite row belongs to a different file. Reload before saving.')
        schema = self._check_schema(connection, token.table, token.schema_token)
        if not isinstance(token.original, tuple) or len(token.original) != len(schema.names):
            raise ValidationError('Use the original row token from a SQLite table page.')
        key_values = tuple(token.original[schema.names.index(key.name)] for key in schema.keys)
        if any(value is None for value in key_values):
            raise ReadOnlyError('A NULL primary-key component cannot identify an editable SQLite row.')
        where = ' AND '.join(f'{key.expression} = ?' for key in schema.keys)
        select = ', '.join(map(_quote, schema.names))
        sql = f'SELECT {select} FROM {_qualified(schema.table.name)} WHERE {where} LIMIT 2'
        with closing(connection.execute(sql, key_values)) as cursor:
            found = cursor.fetchmany(2)
        if len(found) != 1 or not all(_same_value(before, after)
                                      for before, after in zip(token.original, found[0])):
            raise StaleDataError('The original SQLite row changed or is missing. Reload before saving.')
        return schema, where, key_values

    def _execute_one(
        self, connection: sqlite3.Connection, sql: str, bound: tuple[Value, ...]
    ) -> None:
        with closing(connection.execute(sql, bound)) as cursor:
            if cursor.rowcount != 1:
                raise ConstraintError('SQLite did not apply the requested change to exactly one row.')

    def update(self, row: RowToken | None, changes: Mapping[str, Value]) -> None:
        """Update a row only if its identity and every original value still match."""
        with self._mutation() as connection:
            schema, where, key_values = self._original_key(connection, row)
            columns, bound = self._fields(schema, changes)
            if not columns:
                raise ValidationError('Supply at least one changed SQLite column.')
            assignments = ', '.join(f'{column} = ?' for column in columns)
            sql = f'UPDATE OR ABORT {_qualified(schema.table.name)} SET {assignments} WHERE {where}'
            self._execute_one(connection, sql, (*bound, *key_values))

    def delete(self, row: RowToken | None) -> None:
        """Delete a row only if its identity and every original value still match."""
        with self._mutation() as connection:
            schema, where, key_values = self._original_key(connection, row)
            sql = f'DELETE FROM {_qualified(schema.table.name)} WHERE {where}'
            self._execute_one(connection, sql, key_values)
