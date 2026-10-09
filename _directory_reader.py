"""Immutable, streamed directory-index readers with legacy-cache compatibility.

Readers own one SQLite read transaction. A scan can replace/prune generations
without changing the data a displayed Snapshot sees. Scoped lookups use folder IDs
and only reconstruct full Path values for the returned rows.
"""
from collections.abc import Sequence
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock
from ._directory_metadata import Entry
from .operations import check_cancelled, OperationCancelled
from ._directory_search import search_sql, search_words


def _entry(row):
    return Entry(Path(row[0]), bool(row[1]), row[2], row[3], bool(row[4]), tuple(json.loads(row[5])))


class SqlEntries(Sequence):
    """An immutable SQLite read snapshot; entries are streamed rather than all loaded.

    The read transaction keeps an older displayed generation valid during rebuilds
    and cleanup. It is released when the owning Snapshot/iterator is collected.
    """
    def __init__(self, database, generation, *, parent=None, connection=None, scope=None):
        self.connection = connection or sqlite3.connect(f'{database.as_uri()}?mode=ro', uri=True, check_same_thread=False)
        self.connection.execute('PRAGMA query_only=ON')
        self.connection.create_function('search_words', 1, search_words, deterministic=True)
        if connection is None:
            self.connection.execute('BEGIN')
            # Pin the immutable read transaction without counting every entry.
            self.connection.execute('SELECT 1 FROM scans WHERE id=?',(generation,)).fetchone()
        self.generation = generation
        self.parent = parent
        self.compact = bool(self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='indexed_entries'").fetchone())
        self.table = 'indexed_entries' if self.compact else 'entries'
        self.parent_filter = ('parent_id=(SELECT id FROM folder_paths WHERE path=?)'
                              if self.compact else 'parent=?')
        self.lock = RLock()
        self.where = 'generation=?' + (' AND '+self.parent_filter if parent is not None else '')
        self.parameters = (generation,) + ((str(parent),) if parent is not None else ())
        self.scope = scope
        if scope is not None:
            prefix = str(scope).rstrip(os.sep) + os.sep
            if self.compact:
                self.where += (' AND parent_id IN (SELECT id FROM folder_paths '
                               'WHERE path=? OR (path>=? AND path<?))')
                self.parameters += (str(scope), prefix, prefix[:-1] + chr(ord(os.sep) + 1))
            else:
                self.where += ' AND path>=? AND path<?'
                self.parameters += (prefix, prefix[:-1] + chr(ord(os.sep) + 1))
        self._count = None

    @property
    def count(self):
        with self.lock:
            if self._count is None:
                self._count = self.connection.execute(
                    f'SELECT count(*) FROM {"generation_entries" if self.compact else "entries"} WHERE {self.where}', self.parameters).fetchone()[0]
            return self._count

    def __len__(self):
        return self.count

    def _rows(self, extra='', parameters=(), *, order='sort_key,path', cancelled=lambda: False,
              limit=None, offset=0):
        with self.lock:
            self.connection.set_progress_handler(lambda: int(cancelled()), 10_000)
            try:
                cursor = self.connection.execute(
                    f'SELECT path,directory,size,modified,symlink,identity FROM {self.table}'
                    + f' WHERE {self.where} '
                    + extra + f' ORDER BY {order}' + (' LIMIT ? OFFSET ?' if limit is not None else ''),
                    self.parameters + parameters + ((limit, offset) if limit is not None else ()))
                for row in cursor:
                    check_cancelled(cancelled)
                    yield _entry(row)
            except sqlite3.OperationalError:
                if cancelled():
                    raise OperationCancelled('Search cancelled; the saved index is still available') from None
                raise
            finally:
                if 'cursor' in locals():
                    cursor.close()
                self.connection.set_progress_handler(None, 0)

    def __iter__(self):
        return self._rows()

    def __getitem__(self, index):
        if isinstance(index, slice):
            from itertools import islice
            start, stop, step = index.indices(self.count)
            if step < 0:
                return tuple(self)[index]
            return tuple(islice(iter(self), start, stop, step))
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError(index)
        with self.lock:
            row = self.connection.execute(
                f'SELECT path,directory,size,modified,symlink,identity FROM {self.table} WHERE {self.where} '
                'ORDER BY sort_key,path LIMIT 1 OFFSET ?', self.parameters + (index,)).fetchone()
            return _entry(row)

    def search(self, name, *, cancelled=lambda: False):
        condition, parameters = search_sql(name)
        return tuple(self._rows('AND '+condition, parameters, cancelled=cancelled))

    def by_depth(self):
        return self._rows(order='length(path) DESC,path')

    def children(self, path, limit=None):
        return tuple(self._rows('AND '+self.parent_filter, (str(path),), limit=limit))

    def get(self, path):
        path = Path(path)
        return next(self._rows('AND '+self.parent_filter+' AND path=?', (str(path.parent), str(path))), None)

    def search_page(self, name, offset=0, limit=500, *, cancelled=lambda: False, sort='path', descending=False):
        if offset < 0 or limit < 1:
            raise ValueError('Search page requires a nonnegative offset and positive limit')
        columns = {'path': 'sort_key', 'name': 'name_fold', 'size': 'size',
                   'type': 'CASE WHEN symlink THEN 2 WHEN directory THEN 1 ELSE 0 END'}
        if sort not in columns:
            raise ValueError(f'Unsupported search sort {sort}')
        order = columns[sort] + (' DESC' if descending else ' ASC') + ',sort_key,path'
        condition, parameters = search_sql(name)
        with self.lock:
            self.connection.set_progress_handler(lambda: int(cancelled()), 10_000)
            try:
                check_cancelled(cancelled)
                total = self.connection.execute(f'SELECT count(*) FROM {self.table} WHERE {self.where} AND {condition}',
                                                self.parameters + parameters).fetchone()[0]
            except sqlite3.OperationalError:
                if cancelled():
                    raise OperationCancelled('Search cancelled; the saved index is still available') from None
                raise
            finally:
                self.connection.set_progress_handler(None, 0)
        matches = tuple(self._rows('AND '+condition, parameters,
                                   cancelled=cancelled, limit=limit, offset=offset, order=order))
        return matches, total

    def folder_stats(self, paths=None, *, cancelled=lambda: False, stale=False, children_of=None):
        from .filesystem import FolderStats
        values = {}
        with self.lock:
            if not self.connection.execute("SELECT 1 FROM sqlite_master WHERE name='folder_totals'").fetchone():
                return values  # An old cache will be upgraded by the next scan.
            extra = ''
            parameters = (self.generation,)
            if children_of is not None:
                if paths is not None:
                    raise ValueError('Choose explicit paths or immediate child folders')
                # The browser needs one level, not every descendant's JSON totals.
                # Both the address lookup and totals lookup have persistent indexes.
                if self.compact:
                    extra = (' AND path IN (SELECT path FROM folder_paths WHERE path=? OR '
                             'parent_id=(SELECT id FROM folder_paths WHERE path=?))')
                    parameters += (str(children_of), str(children_of))
                else:
                    extra = (' AND (path=? OR path IN (SELECT path FROM folders '
                             'WHERE generation=? AND parent=?))')
                    parameters += (str(children_of), self.generation, str(children_of))
            elif paths is not None:
                paths = tuple(paths)
                if not paths:
                    return values
                extra = ' AND path IN (' + ','.join('?' for _ in paths) + ')'
                parameters += tuple(str(path) for path in paths)
            elif self.scope is not None:
                prefix = str(self.scope).rstrip(os.sep) + os.sep
                extra = ' AND (path=? OR (path>=? AND path<?))'
                parameters += (str(self.scope), prefix, prefix[:-1] + chr(ord(os.sep) + 1))
            self.connection.set_progress_handler(lambda: int(cancelled()), 10_000)
            try:
                source, stamp = 'folder_totals', 'scanned_at'
                if self.connection.execute("SELECT 1 FROM sqlite_master WHERE name='folder_checks'").fetchone():
                    source = ('(SELECT t.*,c.checked_at FROM folder_totals t LEFT JOIN folder_checks c '
                              'ON c.generation=t.generation AND c.path=t.path)')
                    stamp = 'coalesce(checked_at,scanned_at)'
                for row in self.connection.execute(f'SELECT path,size,files,folders,skipped,extensions,complete,{stamp} '
                                                   f'FROM {source} WHERE generation=?' + extra, parameters):
                    check_cancelled(cancelled)
                    path, size, files, folders, skipped, extensions, complete, stamp = row
                    values[Path(path)] = FolderStats(size, files, folders, skipped, json.loads(extensions), bool(complete), stamp, stale)
            except sqlite3.OperationalError:
                check_cancelled(cancelled)
                raise
            finally:
                self.connection.set_progress_handler(None, 0)
        return values

    def __del__(self):
        connection = getattr(self, 'connection', None)
        if connection is not None:
            connection.close()


class SqlDirectories(Sequence):
    """Folder fingerprints from the same immutable read transaction as entries."""
    def __init__(self, entries):
        self.entries = entries
        self.where = 'generation=? AND identity IS NOT NULL'
        self.parameters = (entries.generation,)
        if entries.scope is not None:
            prefix = str(entries.scope).rstrip(os.sep) + os.sep
            self.where += ' AND (path=? OR (path>=? AND path<?))'
            self.parameters += (str(entries.scope), prefix, prefix[:-1] + chr(ord(os.sep) + 1))

    def __len__(self):
        with self.entries.lock:
            return self.entries.connection.execute(
                f'SELECT count(*) FROM folders WHERE {self.where}',
                self.parameters).fetchone()[0]

    def __iter__(self):
        with self.entries.lock:
            cursor = self.entries.connection.execute(
                f'SELECT path,identity FROM folders WHERE {self.where} ORDER BY path',
                self.parameters)
            try:
                for path, identity in cursor:
                    yield Path(path), tuple(json.loads(identity))
            finally:
                cursor.close()

    def __getitem__(self, index):
        from itertools import islice
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            if step < 0:
                return tuple(self)[index]
            return tuple(islice(iter(self), start, stop, step))
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        return next(islice(iter(self), index, index + 1))
