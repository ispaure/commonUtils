"""Headless inspection and editing for existing local SQLite resources."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from .database import Database, Transaction
from .model import (
    All, Any, BusyError, CancelledError, Column, ConstraintError, Filter, Page, Predicate,
    ReadOnlyError, Row, RowToken, Sort, SQLiteError, StaleDataError, Table, ValidationError,
    Value, parse_value,
)

__all__ = [
    'All', 'Any', 'BusyError', 'CancelledError', 'Column', 'ConstraintError', 'Database',
    'Filter', 'Page', 'Predicate', 'ReadOnlyError', 'Row', 'RowToken', 'Sort', 'SQLiteError',
    'StaleDataError', 'Table', 'Transaction', 'ValidationError', 'Value', 'parse_value',
]
