"""SQLite directory generations with durable per-folder scan checkpoints."""
from collections.abc import Sequence
from contextlib import contextmanager, closing
import json
import os
from pathlib import Path
import sqlite3
import sys
from threading import RLock
from time import sleep, time

from ._directory_metadata import Entry, Snapshot, fingerprint
from .operations import check_cancelled, OperationCancelled
from .traversal import natural_path_key
from .storage import cache_directory
from ._directory_totals import store_folder_stats


def directory_index_path():
    return cache_directory(create=False) / 'directory-index.sqlite3'


def _legacy_directory_index_path():
    if sys.platform == 'darwin':
        recent = Path.home() / 'Library' / 'Caches' / 'commonUtils' / 'directory-index.sqlite3'
        if recent.is_file():
            return recent
        folder = Path.home() / 'Library' / 'Application Support'
    elif sys.platform == 'win32':
        folder = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    else:
        folder = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
    return folder / 'commonUtils' / 'directory-index.sqlite3'


def _sort_key(path):
    return _encode_sort_parts(natural_path_key(path))


def _encode_sort_parts(parts):
    result = bytearray()
    for part in parts:
        if isinstance(part, int):
            number = str(part).encode('ascii')
            result.extend(b'\x01' + len(number).to_bytes(4, 'big') + number + b'\0')
        else:
            result.extend(b'\x02' + part.encode('utf-8', 'surrogatepass') + b'\0')
    return bytes(result)


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
        if connection is None:
            self.connection.execute('BEGIN')
        self.generation = generation
        self.parent = parent
        self.lock = RLock()
        self.where = 'generation=?' + (' AND parent=?' if parent is not None else '')
        self.parameters = (generation,) + ((str(parent),) if parent is not None else ())
        self.scope = scope
        if scope is not None:
            prefix = str(scope).rstrip(os.sep) + os.sep
            self.where += ' AND path>=? AND path<?'
            self.parameters += (prefix, prefix[:-1] + chr(ord(os.sep) + 1))
        self.count = self.connection.execute(f'SELECT count(*) FROM entries WHERE {self.where}', self.parameters).fetchone()[0]

    def __len__(self):
        return self.count

    def _rows(self, extra='', parameters=(), *, order='sort_key,path', cancelled=lambda: False,
              limit=None, offset=0):
        with self.lock:
            self.connection.set_progress_handler(lambda: int(cancelled()), 10_000)
            try:
                cursor = self.connection.execute(
                    f'SELECT path,directory,size,modified,symlink,identity FROM entries WHERE {self.where} '
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
                f'SELECT path,directory,size,modified,symlink,identity FROM entries WHERE {self.where} '
                'ORDER BY sort_key,path LIMIT 1 OFFSET ?', self.parameters + (index,)).fetchone()
            return _entry(row)

    def search(self, name, *, cancelled=lambda: False):
        return tuple(self._rows('AND instr(name_fold,?)>0', (name.casefold(),), cancelled=cancelled))

    def by_depth(self):
        return self._rows(order='length(path) DESC,path')

    def children(self, path, limit=None):
        return tuple(self._rows('AND parent=?', (str(path),), limit=limit))

    def get(self, path):
        return next(self._rows('AND path=?', (str(path),)), None)

    def search_page(self, name, offset=0, limit=500, *, cancelled=lambda: False, sort='path', descending=False):
        if offset < 0 or limit < 1:
            raise ValueError('Search page requires a nonnegative offset and positive limit')
        columns = {'path': 'sort_key', 'name': 'name_fold', 'size': 'size',
                   'type': 'CASE WHEN symlink THEN 2 WHEN directory THEN 1 ELSE 0 END'}
        if sort not in columns:
            raise ValueError(f'Unsupported search sort {sort}')
        order = columns[sort] + (' DESC' if descending else ' ASC') + ',sort_key,path'
        with self.lock:
            self.connection.set_progress_handler(lambda: int(cancelled()), 10_000)
            try:
                check_cancelled(cancelled)
                total = self.connection.execute(f'SELECT count(*) FROM entries WHERE {self.where} AND instr(name_fold,?)>0',
                                                self.parameters + (name.casefold(),)).fetchone()[0]
            except sqlite3.OperationalError:
                if cancelled():
                    raise OperationCancelled('Search cancelled; the saved index is still available') from None
                raise
            finally:
                self.connection.set_progress_handler(None, 0)
        matches = tuple(self._rows('AND instr(name_fold,?)>0', (name.casefold(),),
                                   cancelled=cancelled, limit=limit, offset=offset, order=order))
        return matches, total

    def folder_stats(self, paths=None, *, cancelled=lambda: False, stale=False):
        from .filesystem import FolderStats
        values = {}
        with self.lock:
            if not self.connection.execute("SELECT 1 FROM sqlite_master WHERE name='folder_totals'").fetchone():
                return values  # An old cache will be upgraded by the next scan.
            extra = ''
            parameters = (self.generation,)
            if paths is not None:
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
                for row in self.connection.execute('SELECT path,size,files,folders,skipped,extensions,complete,scanned_at '
                                                   'FROM folder_totals WHERE generation=?' + extra, parameters):
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


class DirectoryCache:
    """Persistent index with no entry-count or root-count cutoff.

    Completed generations stay available until a validated replacement is ready.
    Cancelled scans keep finished folders; interrupted folders restart on resume.
    Different windows/processes serialize writers, with cancellable lock waits.
    """
    def __init__(self, *, database=None):
        self.database = (Path(database) if database is not None else directory_index_path()).absolute()
        self._legacy_database = _legacy_directory_index_path() if database is None else None
        self._work_lock = RLock()
        self._state_lock = RLock()
        self._revision = 0
        self._invalidations = {}
        self._validated_roots = {}
        self._validated_times = {}

    def invalidate(self, root=None):
        # Browser refresh runs on the GUI thread. Avoid waiting for a worker or DB.
        with self._state_lock:
            self._revision += 1
            self._invalidations[None if root is None else Path(root).absolute()] = self._revision

    @contextmanager
    def _writer(self, cancelled):
        while not self._work_lock.acquire(timeout=.05):
            check_cancelled(cancelled)
        try:
            check_cancelled(cancelled)
            self.database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self.database.with_suffix('.lock').open('a+b') as lock:
                if sys.platform == 'win32':
                    import msvcrt
                    lock.seek(0, 2)
                    if not lock.tell():
                        lock.write(b'0'); lock.flush()
                else:
                    import fcntl
                while True:
                    check_cancelled(cancelled)
                    try:
                        if sys.platform == 'win32':
                            lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        sleep(.05)
                    except OSError as error:
                        if sys.platform != 'win32' or error.errno not in (13, 11, 36):
                            raise
                        sleep(.05)
                try:
                    self._migrate_legacy(cancelled)
                    connection = sqlite3.connect(self.database)
                    try:
                        connection.execute('PRAGMA journal_mode=WAL')
                        connection.execute('PRAGMA foreign_keys=ON')
                        self._schema(connection)
                        connection.set_progress_handler(lambda: int(cancelled()), 10_000)
                        yield connection
                    except sqlite3.OperationalError:
                        if cancelled():
                            raise OperationCancelled('Operation cancelled; saved folder checkpoints can be resumed') from None
                        raise
                    finally:
                        connection.close()
                finally:
                    if sys.platform == 'win32':
                        lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        finally:
            self._work_lock.release()

    def _migrate_legacy(self, cancelled):
        # Called under the destination writer lock. SQLite backup includes committed
        # WAL data even when an older application is still using the original DB.
        # Retain the original for older consumers and recovery; never overwrite an
        # existing canonical cache or import into explicitly supplied databases.
        source = self._legacy_database
        if source is None or source == self.database or self.database.exists() or not source.is_file():
            return
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(dir=self.database.parent, prefix='.index-migration-', delete=False) as stream:
            staged = Path(stream.name)
        try:
            with closing(sqlite3.connect(f'{source.absolute().as_uri()}?mode=ro', uri=True)) as old:
                with closing(sqlite3.connect(staged)) as new:
                    old.backup(new, pages=128, progress=lambda *args: check_cancelled(cancelled), sleep=.05)
                    if new.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise RuntimeError('Existing directory index failed its integrity check')
            check_cancelled(cancelled)
            staged.replace(self.database)
        finally:
            staged.unlink(missing_ok=True)

    @staticmethod
    def _schema(db):
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1, 2):
            raise RuntimeError(f'Unsupported directory index version {version}; choose another index file')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS scans(id INTEGER PRIMARY KEY, root TEXT NOT NULL,
                recursive INTEGER NOT NULL, scanned_at REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS roots(root TEXT NOT NULL, recursive INTEGER NOT NULL,
                completed INTEGER, building INTEGER, PRIMARY KEY(root,recursive));
            CREATE TABLE IF NOT EXISTS entries(generation INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                path TEXT NOT NULL, parent TEXT NOT NULL, name_fold TEXT NOT NULL,
                directory INTEGER NOT NULL, size INTEGER NOT NULL, modified INTEGER NOT NULL,
                symlink INTEGER NOT NULL, identity TEXT NOT NULL, sort_key BLOB NOT NULL,
                PRIMARY KEY(generation,path));
            CREATE INDEX IF NOT EXISTS entry_parent ON entries(generation,parent);
            CREATE INDEX IF NOT EXISTS entry_order ON entries(generation,sort_key,path);
            CREATE INDEX IF NOT EXISTS entry_name_order ON entries(generation,name_fold,sort_key,path);
            CREATE TABLE IF NOT EXISTS folders(generation INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                path TEXT NOT NULL,parent TEXT NOT NULL,status TEXT NOT NULL,identity TEXT,
                PRIMARY KEY(generation,path));
            CREATE INDEX IF NOT EXISTS folder_pending ON folders(generation,status,length(path),path);
            CREATE INDEX IF NOT EXISTS folder_queue_order ON folders(generation,status,length(path),path);
            CREATE TABLE IF NOT EXISTS errors(generation INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                path TEXT NOT NULL,error TEXT NOT NULL,PRIMARY KEY(generation,path));
            CREATE TABLE IF NOT EXISTS folder_totals(generation INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                path TEXT NOT NULL,size INTEGER NOT NULL,files INTEGER NOT NULL,folders INTEGER NOT NULL,
                skipped INTEGER NOT NULL,extensions TEXT NOT NULL,complete INTEGER NOT NULL,scanned_at REAL NOT NULL,
                PRIMARY KEY(generation,path));
            PRAGMA user_version=2;
        ''')

    @staticmethod
    def _folder_identity(folder, root):
        info = folder.stat() if folder == root else folder.lstat()
        if folder != root and (folder.is_symlink() or folder.is_junction()):
            raise OSError('Directory became a link during scanning')
        if not folder.is_dir():
            raise NotADirectoryError(folder)
        return json.dumps(fingerprint(info))

    def _validate(self, db, generation, root, cancelled, report, *, root_only=False, check_files=True):
        unchanged = True
        for (path,) in db.execute('SELECT path FROM errors WHERE generation=?', (generation,)).fetchall():
            db.execute("UPDATE folders SET status='pending' WHERE generation=? AND (path=? OR path=?)",
                       (generation, path, str(Path(path).parent)))
        rows = db.execute('SELECT path,identity,status FROM folders WHERE generation=?' +
                          (' AND path=?' if root_only else '') + ' ORDER BY path',
                          (generation, str(root)) if root_only else (generation,))
        count = 0
        for text, expected, status in rows:
            check_cancelled(cancelled)
            valid = status == 'done'
            try:
                valid = valid and self._folder_identity(Path(text), root) == expected
                if valid and check_files:
                    children = db.execute('SELECT path,identity FROM entries WHERE generation=? AND parent=?', (generation, text))
                    for child, identity in children:
                        check_cancelled(cancelled)
                        self._checked_entries += 1
                        report(self._checked_entries, 0, f'Checking file metadata · {text}')
                        if json.dumps(fingerprint(Path(child).lstat())) != identity:
                            valid = False
                            break
            except OSError:
                valid = False
            if not valid:
                unchanged = False
                db.execute("UPDATE folders SET status='pending' WHERE generation=? AND path=?", (generation, text))
            count += 1
            report(self._checked_entries, 0, f'Checking indexed folder {text}')
        db.commit()
        return unchanged

    @staticmethod
    def _remove_tree(db, generation, folder):
        # A separator-aware prefix handles '%'/'_' in literal folder names safely.
        prefix = folder.rstrip(os.sep) + os.sep
        for table in ('entries', 'folders', 'errors'):
            # The parent has already reconciled its entries. Preserve a new file
            # or link at the old directory's path while deleting its old children.
            if table == 'entries':
                db.execute('DELETE FROM entries WHERE generation=? AND substr(path,1,?)=?',
                           (generation, len(prefix), prefix))
            else:
                db.execute(f'DELETE FROM {table} WHERE generation=? AND (path=? OR substr(path,1,?)=?)',
                           (generation, folder, len(prefix), prefix))

    def _scan_folder(self, db, generation, root, recursive, folder, cancelled, report):
        text = str(folder)
        # Every child shares the parent's natural-order chunks. Encode those once.
        parts = natural_path_key(text + os.sep)
        sort_prefix, sort_tail = _encode_sort_parts(parts[:-1]), parts[-1]
        for (error_path,) in db.execute('SELECT path FROM errors WHERE generation=?', (generation,)).fetchall():
            if error_path == text or Path(error_path).parent == folder:
                db.execute('DELETE FROM errors WHERE generation=? AND path=?', (generation, error_path))
        db.execute('DELETE FROM entries WHERE generation=? AND parent=?', (generation, text))
        seen = set()
        count = 0
        try:
            before = self._folder_identity(folder, root)
            with os.scandir(folder) as children:
                for child in children:
                    check_cancelled(cancelled)
                    path = Path(child.path)
                    if path in self._excluded_paths:
                        continue
                    try:
                        info = child.stat(follow_symlinks=False)
                        link = child.is_symlink() or path.is_junction()
                        directory = not link and child.is_dir(follow_symlinks=False)
                        identity = json.dumps(fingerprint(info))
                        db.execute('INSERT OR REPLACE INTO entries VALUES(?,?,?,?,?,?,?,?,?,?)',
                                   (generation, str(path), text, path.name.casefold(), directory,
                                    0 if directory or link else info.st_size, info.st_mtime_ns,
                                    link, identity, sort_prefix + _sort_key(sort_tail + path.name)))
                        if directory and recursive:
                            seen.add(str(path))
                            db.execute("INSERT INTO folders VALUES(?,?,?,'pending',NULL) ON CONFLICT(generation,path) "
                                       "DO UPDATE SET status=CASE WHEN folders.identity=? AND folders.status='done' "
                                       "THEN 'done' ELSE 'pending' END", (generation, str(path), text, identity))
                    except OSError as error:
                        db.execute('INSERT OR REPLACE INTO errors VALUES(?,?,?)', (generation, str(path), str(error)))
                    count += 1
                    self._discovered_entries += 1
                    if count % 512 == 0:
                        db.commit()
                    report(self._discovered_entries, 0, f'Indexing {folder} · {count:,} entries in this folder')
            for (old,) in db.execute('SELECT path FROM folders WHERE generation=? AND parent=?', (generation, text)).fetchall():
                if old not in seen:
                    self._remove_tree(db, generation, old)
            # Changes during enumeration require another pass rather than publishing a stale folder.
            after = self._folder_identity(folder, root)
            db.execute('UPDATE folders SET status=?,identity=? WHERE generation=? AND path=?',
                       ('done' if before == after else 'pending', after, generation, text))
        except OSError as error:
            db.execute('INSERT OR REPLACE INTO errors VALUES(?,?,?)', (generation, text, str(error)))
            db.execute("UPDATE folders SET status='error' WHERE generation=? AND path=?", (generation, text))
        finally:
            # Partial entries are saved, but the folder stays pending until a full enumeration finishes.
            db.commit()
            if not cancelled() and time() - self._totals_last > self._totals_interval:
                started = time()
                store_folder_stats(db, generation, root, cancelled)
                db.commit()
                self._totals_last = time()
                self._totals_interval = max(2, min(60, (self._totals_last - started) * 20))
                report(0, 0, 'Saved progressive folder totals')

    def _snapshot(self, db, generation, root, recursive, *, reused=False, resumed=False, complete=True, parent=None,
                  metadata_checked=True, reader=None, cancelled=lambda: False, scope=None):
        if reader is None and not db.execute('SELECT 1 FROM folder_totals WHERE generation=? LIMIT 1', (generation,)).fetchone():
            store_folder_stats(db, generation, root, cancelled)
            db.commit()
        entries = SqlEntries(self.database, generation, parent=parent, connection=reader, scope=scope)
        errors = tuple((Path(path), error) for path, error in db.execute('SELECT path,error FROM errors WHERE generation=?', (generation,)))
        scanned = db.execute('SELECT scanned_at FROM scans WHERE id=?', (generation,)).fetchone()[0]
        directories = SqlDirectories(entries)
        return Snapshot(root, recursive, entries, errors, scanned or time(), directories=directories, reused=reused,
                        validated_at=time(), resumed=resumed, complete=complete, metadata_checked=metadata_checked)

    def get(self, root, recursive=True, *, refresh=False, cancelled=lambda: False,
            report=lambda done, total, message: None, validate_files=True, reuse_for=0):
        root = Path(root).absolute()
        if not root.is_dir():
            raise NotADirectoryError(root)
        if root.resolve() == self.database.parent.resolve():
            raise ValueError('The directory index storage folder cannot index itself. Choose another folder.')
        report(0, 0, 'Waiting for index writer…')
        with self._writer(cancelled) as db:
            self._discovered_entries = self._checked_entries = 0
            self._totals_interval = 2
            with self._state_lock:
                revision = self._revision
                checked_revision = self._validated_roots.get((root, recursive), 0)
                dirty = any(mark > checked_revision and (path is None or path == root or path in root.parents or root in path.parents)
                            for path, mark in self._invalidations.items())
            self._totals_last = time()
            real_root = root.resolve()
            self._excluded_paths = set()
            for path in (self.database.parent, self.database, self.database.with_suffix('.lock'),
                         Path(str(self.database) + '-wal'), Path(str(self.database) + '-shm')):
                try:
                    self._excluded_paths.add(root / path.resolve().relative_to(real_root))
                except ValueError:
                    pass
            db.execute('INSERT OR IGNORE INTO roots(root,recursive) VALUES(?,?)', (str(root), recursive))
            completed, building = db.execute('SELECT completed,building FROM roots WHERE root=? AND recursive=?', (str(root), recursive)).fetchone()
            if recursive and not completed and not building and not refresh:
                # Seed a newly browsed subtree from a completed ancestor index.
                # Validation still checks every descendant before reuse, but names
                # and unchanged folders need no second filesystem enumeration.
                ancestors = tuple(str(path) for path in root.parents)
                if ancestors:
                    covering = db.execute('SELECT completed FROM roots WHERE recursive=1 AND completed IS NOT NULL '
                                          'AND root IN (' + ','.join('?' for _ in ancestors) + ') ORDER BY length(root) DESC LIMIT 1', ancestors).fetchone()
                    if covering:
                        completed = db.execute('INSERT INTO scans(root,recursive,scanned_at) '
                                               'SELECT ?,1,scanned_at FROM scans WHERE id=?', (str(root), covering[0])).lastrowid
                        prefix = str(root).rstrip(os.sep) + os.sep
                        upper = prefix[:-1] + chr(ord(os.sep) + 1)
                        db.execute('INSERT INTO entries SELECT ?,path,parent,name_fold,directory,size,modified,symlink,identity,sort_key '
                                   'FROM entries WHERE generation=? AND path>=? AND path<?', (completed, covering[0], prefix, upper))
                        db.execute('INSERT INTO folders SELECT ?,path,parent,status,identity FROM folders WHERE generation=? '
                                   'AND (path=? OR (path>=? AND path<?))', (completed, covering[0], str(root), prefix, upper))
                        if not db.execute('SELECT 1 FROM folders WHERE generation=? AND path=?', (completed, str(root))).fetchone():
                            db.execute("INSERT INTO folders VALUES(?,?,?,'pending',NULL)", (completed, str(root), ''))
                        db.execute('UPDATE roots SET completed=? WHERE root=? AND recursive=1', (completed, str(root)))
                        db.commit()
            with self._state_lock:
                recently_checked = time() - self._validated_times.get((root, recursive), 0) < reuse_for
            if completed and not building and not refresh and not dirty and recently_checked:
                return self._snapshot(db, completed, root, recursive, reused=True, cancelled=cancelled)

            if not recursive and not completed and not building and not refresh and not dirty:
                full = db.execute('SELECT completed FROM roots WHERE root=? AND recursive=1', (str(root),)).fetchone()
                if full and full[0] and self._validate(db, full[0], root, cancelled, report, root_only=True, check_files=validate_files):
                    return self._snapshot(db, full[0], root, False, reused=True, parent=root, metadata_checked=validate_files, cancelled=cancelled)
            if completed and not building and not refresh and not dirty:
                if self._validate(db, completed, root, cancelled, report, check_files=validate_files):
                    if validate_files:
                        with self._state_lock:
                            self._validated_times[(root, recursive)] = time()
                    return self._snapshot(db, completed, root, recursive, reused=True, metadata_checked=validate_files, cancelled=cancelled)
            resumed = bool(building) and not refresh
            if refresh and building:
                db.execute('DELETE FROM scans WHERE id=?', (building,))
                building = None
            # Validate on disk using one folder at a time. A completed generation is
            # immutable for readers, so validation/status changes happen in a work copy.
            if not building:
                building = db.execute('INSERT INTO scans(root,recursive) VALUES(?,?)', (str(root), recursive)).lastrowid
                if completed and not refresh:
                    db.execute('INSERT INTO entries SELECT ?,path,parent,name_fold,directory,size,modified,symlink,identity,sort_key FROM entries WHERE generation=?', (building, completed))
                    db.execute('INSERT INTO folders SELECT ?,path,parent,status,identity FROM folders WHERE generation=?', (building, completed))
                else:
                    db.execute("INSERT INTO folders VALUES(?,?,?,'pending',NULL)", (building, str(root), ''))
                db.execute('UPDATE roots SET building=? WHERE root=? AND recursive=?', (building, str(root), recursive))
                db.commit()
            # Finish discovering missing branches before rechecking old metadata.
            # Completed folders are validated after discovery, including on resume.
            unchanged = False
            if not resumed and completed:
                unchanged = self._validate(db, building, root, cancelled, report)
            if unchanged and completed and not resumed and not dirty and not refresh:
                db.execute('UPDATE roots SET building=NULL WHERE root=? AND recursive=?', (str(root), recursive))
                db.execute('DELETE FROM scans WHERE id=?', (building,))
                db.commit()
                return self._snapshot(db, completed, root, recursive, reused=True, cancelled=cancelled)
            report(0, 0, 'Resuming saved folder checkpoints…' if resumed else 'Updating persistent index…')
            def discover_pending():
                while True:
                    check_cancelled(cancelled)
                    # Batches avoid sorting the whole pending tree for every folder.
                    rows = db.execute("SELECT path FROM folders WHERE generation=? AND status='pending' AND identity IS NULL ORDER BY length(path),path LIMIT 256", (building,)).fetchall()
                    if not rows:
                        rows = db.execute("SELECT path FROM folders WHERE generation=? AND status='pending' ORDER BY length(path),path LIMIT 256", (building,)).fetchall()
                    if not rows:
                        break
                    for (path,) in rows:
                        check_cancelled(cancelled)
                        # A parent reconciliation can remove a previously queued child.
                        if db.execute("SELECT 1 FROM folders WHERE generation=? AND path=? AND status='pending'", (building, path)).fetchone():
                            self._scan_folder(db, building, root, recursive, Path(path), cancelled, report)
            discover_pending()
            if resumed:
                self._validate(db, building, root, cancelled, report)
                discover_pending()
            check_cancelled(cancelled)
            # Revalidate folders/files changed during this pass before calling it complete.
            valid = self._validate(db, building, root, cancelled, report)
            errors = db.execute('SELECT count(*) FROM errors WHERE generation=?', (building,)).fetchone()[0]
            store_folder_stats(db, building, root, cancelled)
            db.execute('UPDATE scans SET scanned_at=? WHERE id=?', (time(), building))
            complete = valid and not errors
            if complete:
                db.execute('UPDATE roots SET completed=?,building=NULL WHERE root=? AND recursive=?', (building, str(root), recursive))
                if completed:
                    db.execute('DELETE FROM scans WHERE id=?', (completed,))
            db.commit()
            with self._state_lock:
                if revision == self._revision and complete:
                    self._validated_roots[(root, recursive)] = revision
                    self._validated_times[(root, recursive)] = time()
            return self._snapshot(db, building, root, recursive, resumed=resumed, complete=complete, cancelled=cancelled)

    def peek(self, root, recursive=True, *, partial=True, cancelled=lambda: False):
        """Read cached data immediately, without locks, validation or filesystem scan.

        Call on a worker. Saved metadata is explicitly stale until get() validates it.
        Disconnected roots can still be read here without deleting their records.
        """
        check_cancelled(cancelled)
        if not self.database.is_file():
            return None
        root = Path(root).absolute()
        db = sqlite3.connect(f'{self.database.as_uri()}?mode=ro', uri=True, check_same_thread=False)
        try:
            db.execute('BEGIN')
            row = db.execute('SELECT root,completed,building FROM roots WHERE root=? AND recursive=?', (str(root), recursive)).fetchone()
            if row is None and not recursive:
                row = db.execute('SELECT root,completed,building FROM roots WHERE root=? AND recursive=1', (str(root),)).fetchone()
            if row is None and recursive:
                ancestors = tuple(str(path) for path in root.parents)
                if ancestors:
                    row = db.execute('SELECT root,completed,building FROM roots WHERE recursive=1 AND root IN (' +
                                     ','.join('?' for _ in ancestors) + ') AND (completed IS NOT NULL OR building IS NOT NULL) '
                                     'ORDER BY length(root) DESC LIMIT 1', ancestors).fetchone()
            if row is None or not (row[1] or row[2] and partial):
                db.close()
                return None
            generation = row[2] if partial and row[2] else row[1]
            scope = root if row[0] != str(root) else None
            snapshot = self._snapshot(db, generation, root, recursive, complete=generation == row[1],
                                      metadata_checked=False, reader=db, scope=scope, parent=root if not recursive else None)
            return snapshot  # Snapshot owns this read transaction, including its lifetime.
        except BaseException:
            db.close()
            raise

    def status(self, root, recursive=True):
        """Read saved work for cancellation UI; does not create an index file."""
        if not self.database.exists():
            return None
        with sqlite3.connect(f'{self.database.as_uri()}?mode=ro', uri=True) as db:
            db.execute('BEGIN')
            row = db.execute('SELECT building FROM roots WHERE root=? AND recursive=?',
                             (str(Path(root).absolute()), recursive)).fetchone()
            if not row or not row[0]:
                return None
            generation = row[0]
            done, pending = db.execute("SELECT coalesce(sum(status='done'),0),coalesce(sum(status!='done'),0) FROM folders WHERE generation=?", (generation,)).fetchone()
            entries = db.execute('SELECT count(*) FROM entries WHERE generation=?', (generation,)).fetchone()[0]
            return {'folders_done': done, 'folders_remaining': pending, 'entries': entries}

    def clear(self, root=None, *, cancelled=lambda: False):
        """Remove saved completed/partial indices; existing displayed snapshots remain readable."""
        if not self.database.exists():
            return
        with self._writer(cancelled) as db:
            for text, recursive, completed, building in db.execute('SELECT * FROM roots').fetchall():
                check_cancelled(cancelled)
                path = Path(text)
                target = Path(root).absolute() if root is not None else None
                if target is None or path == target or path in target.parents or target in path.parents:
                    db.execute('DELETE FROM roots WHERE root=? AND recursive=?', (text, recursive))
                    for generation in (completed, building):
                        if generation:
                            db.execute('DELETE FROM scans WHERE id=?', (generation,))
            check_cancelled(cancelled)
            db.commit()
