"""Data values and validation for the local SQLite resource API."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from dataclasses import dataclass
import math
import re
from typing import TypeAlias


Value: TypeAlias = None | int | float | str | bytes


class SQLiteError(Exception):
    """An SQLite resource operation failed."""


class ReadOnlyError(SQLiteError):
    """The connection, SQL statement, or target does not allow this write."""


class ValidationError(SQLiteError):
    """A request does not meet the SQLite API contract."""


class StaleDataError(SQLiteError):
    """The file, schema, or original row has changed since it was read."""


class BusyError(SQLiteError):
    """SQLite could not acquire a lock within the configured timeout."""


class ConstraintError(SQLiteError):
    """SQLite rejected or skipped a mutation."""


class CancelledError(SQLiteError):
    """The caller cancelled an operation."""


@dataclass(frozen=True)
class Column:
    name: str
    declared_type: str
    not_null: bool
    default: str | None
    pk_order: int
    hidden: int


@dataclass(frozen=True)
class Table:
    name: str
    kind: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...]
    schema_token: str
    editable: bool
    read_only_reason: str | None


@dataclass(frozen=True)
class RowToken:
    """Original values and identity needed to compare before a write."""

    table: str
    schema_token: str
    file_identity: tuple[int, int]
    original: tuple[Value, ...]


@dataclass(frozen=True)
class Row:
    columns: tuple[str, ...]
    values: tuple[Value, ...]
    token: RowToken | None = None

    def __getitem__(self, column: str) -> Value:
        try:
            index = self.columns.index(column)
        except ValueError as error:
            raise KeyError(column) from error
        return self.values[index]


@dataclass(frozen=True)
class Page:
    columns: tuple[str, ...]
    rows: tuple[Row, ...]
    has_more: bool
    offset: int
    limit: int


@dataclass(frozen=True)
class Sort:
    column: str
    descending: bool = False


@dataclass(frozen=True)
class Filter:
    column: str
    operator: str
    value: Value = None


@dataclass(frozen=True, init=False)
class All:
    filters: tuple['Predicate', ...]

    def __init__(self, *filters: 'Predicate') -> None:
        object.__setattr__(self, 'filters', filters)


@dataclass(frozen=True, init=False)
class Any:
    filters: tuple['Predicate', ...]

    def __init__(self, *filters: 'Predicate') -> None:
        object.__setattr__(self, 'filters', filters)


Predicate: TypeAlias = Filter | All | Any
_INTEGER = re.compile(r'[+-]?[0-9]+')
_REAL = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')
_INTEGER_MIN = -(2 ** 63)
_INTEGER_MAX = 2 ** 63 - 1


def _bind_value(value: Value) -> Value:
    if type(value) not in (type(None), int, float, str, bytes):
        raise ValidationError('Use NULL, an integer, a real, text, or bytes as a SQLite value.')
    if type(value) is int and not _INTEGER_MIN <= value <= _INTEGER_MAX:
        raise ValidationError('SQLite integers must fit in signed 64 bits.')
    if type(value) is float and not math.isfinite(value):
        raise ValidationError('SQLite real input must be finite.')
    if type(value) is str:
        try:
            value.encode('utf-8')
        except UnicodeError as error:
            raise ValidationError('SQLite text must be valid UTF-8.') from error
    return value


def parse_value(kind: str, text: str) -> Value:
    """Parse an explicitly selected SQLite storage class from user input."""
    if not isinstance(text, str):
        raise ValidationError('Enter a text representation for the selected SQLite value type.')
    if kind == 'text':
        return _bind_value(text)
    stripped = text.strip()
    if kind == 'null':
        if stripped and stripped.upper() != 'NULL':
            raise ValidationError('Leave the value empty or enter NULL for a null value.')
        return None
    if kind == 'integer':
        if _INTEGER.fullmatch(stripped) is None:
            raise ValidationError('Enter a signed decimal integer.')
        try:
            return _bind_value(int(stripped))
        except ValueError as error:
            raise ValidationError('SQLite integers must fit in signed 64 bits.') from error
    if kind == 'real':
        if _REAL.fullmatch(stripped) is None:
            raise ValidationError('Enter a finite decimal number.')
        return _bind_value(float(stripped))
    if kind == 'blob':
        try:
            return bytes.fromhex(stripped)
        except ValueError as error:
            raise ValidationError('Enter a BLOB as hexadecimal byte pairs.') from error
    raise ValidationError(f'Unknown SQLite value type {kind!r}.')


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _column(name: str, names: tuple[str, ...]) -> str:
    if not isinstance(name, str) or name not in names:
        raise ValidationError(f'Unknown SQLite column {name!r}.')
    return _quote(name)


_COMPARISONS = {'eq': '=', 'ne': '!=', 'lt': '<', 'le': '<=', 'gt': '>', 'ge': '>='}
_NULLS = {'is_null': 'IS NULL', 'not_null': 'IS NOT NULL'}


def _compile_filter(
    predicate: Predicate, names: tuple[str, ...], parameters: list[Value]
) -> str:
    if isinstance(predicate, (All, Any)):
        joiner, empty = (' AND ', '1') if isinstance(predicate, All) else (' OR ', '0')
        if not predicate.filters:
            return empty
        terms = joiner.join(_compile_filter(item, names, parameters) for item in predicate.filters)
        return f'({terms})'
    if not isinstance(predicate, Filter):
        raise ValidationError('Use Filter, All, or Any to filter a SQLite page.')
    column = _column(predicate.column, names)
    operator = predicate.operator
    if not isinstance(operator, str):
        raise ValidationError('A SQLite filter operator must be text.')
    if operator in _NULLS:
        if predicate.value is not None:
            raise ValidationError('A null test does not take a value.')
        return f'{column} {_NULLS[operator]}'
    if operator in _COMPARISONS:
        if predicate.value is None:
            raise ValidationError('Use is_null or not_null to test for NULL.')
        parameters.append(_bind_value(predicate.value))
        return f'{column} {_COMPARISONS[operator]} ?'
    if operator in ('contains', 'starts_with'):
        if type(predicate.value) is not str:
            raise ValidationError('A text filter needs a text value.')
        parameters.append(_bind_value(predicate.value))
        comparison = '> 0' if operator == 'contains' else '= 1'
        return f"instr({column}, ?) {comparison}"
    raise ValidationError(f'Unknown SQLite filter operator {operator!r}.')
