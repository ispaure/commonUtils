"""SQLite directory generations with durable per-folder scan checkpoints."""
from collections.abc import Sequence
from contextlib import contextmanager
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


def directory_index_path():
    if sys.platform == 'darwin':
        folder = Path.home() / 'Library' / 'Application Support'
    elif sys.platform == 'win32':
        folder = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    else:
        folder = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
    return folder / 'commonUtils' / 'directory-index.sqlite3'


def _sort_key(path):
    result = bytearray()
    for part in natural_path_key(path):
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
    def __init__(self, database, generation, *, parent=None):
        self.connection = sqlite3.connect(f'{database.as_uri()}?mode=ro', uri=True, check_same_thread=False)
        self.connection.execute('PRAGMA query_only=ON')
        self.connection.execute('BEGIN')
        self.generation = generation
        self.parent = parent
        self.lock = RLock()
        self.where = 'generation=?' + (' AND parent=?' if parent is not None else '')
        self.parameters = (generation,) + ((str(parent),) if parent is not None else ())
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

    def children(self, path):
        return tuple(self._rows('AND parent=?', (str(path),)))

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

    def __del__(self):
        connection = getattr(self, 'connection', None)
        if connection is not None:
            connection.close()


class SqlDirectories(Sequence):
    """Folder fingerprints from the same immutable read transaction as entries."""
    def __init__(self, entries):
        self.entries = entries

    def __len__(self):
        with self.entries.lock:
            return self.entries.connection.execute(
                'SELECT count(*) FROM folders WHERE generation=? AND identity IS NOT NULL',
                (self.entries.generation,)).fetchone()[0]

    def __iter__(self):
        with self.entries.lock:
            cursor = self.entries.connection.execute(
                'SELECT path,identity FROM folders WHERE generation=? AND identity IS NOT NULL ORDER BY path',
                (self.entries.generation,))
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
        self._work_lock = RLock()
        self._state_lock = RLock()
        self._revision = 0
        self._invalidations = {}
        self._validated_roots = {}

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

    @staticmethod
    def _schema(db):
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
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
            CREATE INDEX IF NOT EXISTS folder_queue_order ON folders(generation,status,length(path),path);
            CREATE TABLE IF NOT EXISTS errors(generation INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                path TEXT NOT NULL,error TEXT NOT NULL,PRIMARY KEY(generation,path));
            PRAGMA user_version=1;
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
                        if json.dumps(fingerprint(Path(child).lstat())) != identity:
                            valid = False
                            break
            except OSError:
                valid = False
            if not valid:
                unchanged = False
                db.execute("UPDATE folders SET status='pending' WHERE generation=? AND path=?", (generation, text))
            count += 1
            report(count, 0, f'Checking indexed folder {text}')
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
        for (error_path,) in db.execute('SELECT path FROM errors WHERE generation=?', (generation,)).fetchall():
            if error_path == text or Path(error_path).parent == folder:
                db.execute('DELETE FROM errors WHERE generation=? AND path=?', (generation, error_path))
        db.execute('DELETE FROM entries WHERE generation=? AND parent=?', (generation, text))
        db.commit()
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
                                    link, identity, _sort_key(path)))
                        if directory and recursive:
                            seen.add(str(path))
                            db.execute("INSERT INTO folders VALUES(?,?,?,'pending',NULL) ON CONFLICT(generation,path) "
                                       "DO UPDATE SET status=CASE WHEN folders.identity=? AND folders.status='done' "
                                       "THEN 'done' ELSE 'pending' END", (generation, str(path), text, identity))
                    except OSError as error:
                        db.execute('INSERT OR REPLACE INTO errors VALUES(?,?,?)', (generation, str(path), str(error)))
                    count += 1
                    if count % 512 == 0:
                        db.commit()
                    report(count, 0, f'Indexing {folder} · {count:,} entries in this folder')
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

    def _snapshot(self, db, generation, root, recursive, *, reused=False, resumed=False, complete=True, parent=None,
                  metadata_checked=True):
        entries = SqlEntries(self.database, generation, parent=parent)
        errors = tuple((Path(path), error) for path, error in db.execute('SELECT path,error FROM errors WHERE generation=?', (generation,)))
        scanned = db.execute('SELECT scanned_at FROM scans WHERE id=?', (generation,)).fetchone()[0]
        directories = SqlDirectories(entries)
        return Snapshot(root, recursive, entries, errors, scanned or time(), directories=directories, reused=reused,
                        validated_at=time(), resumed=resumed, complete=complete, metadata_checked=metadata_checked)

    def get(self, root, recursive=True, *, refresh=False, cancelled=lambda: False,
            report=lambda done, total, message: None, validate_files=True):
        root = Path(root).absolute()
        if not root.is_dir():
            raise NotADirectoryError(root)
        if root.resolve() == self.database.parent.resolve():
            raise ValueError('The directory index storage folder cannot index itself. Choose another folder.')
        with self._state_lock:
            revision = self._revision
            checked_revision = self._validated_roots.get((root, recursive), 0)
            dirty = any(mark > checked_revision and (path is None or path == root or path in root.parents or root in path.parents)
                        for path, mark in self._invalidations.items())
        with self._writer(cancelled) as db:
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
            if not recursive and not completed and not building and not refresh and not dirty:
                full = db.execute('SELECT completed FROM roots WHERE root=? AND recursive=1', (str(root),)).fetchone()
                if full and full[0] and self._validate(db, full[0], root, cancelled, report, root_only=True, check_files=validate_files):
                    return self._snapshot(db, full[0], root, False, reused=True, parent=root, metadata_checked=validate_files)
            if completed and not building and not refresh and not dirty:
                if self._validate(db, completed, root, cancelled, report, check_files=validate_files):
                    return self._snapshot(db, completed, root, recursive, reused=True, metadata_checked=validate_files)
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
            unchanged = self._validate(db, building, root, cancelled, report)
            if unchanged and completed and not resumed and not dirty and not refresh:
                db.execute('UPDATE roots SET building=NULL WHERE root=? AND recursive=?', (str(root), recursive))
                db.execute('DELETE FROM scans WHERE id=?', (building,))
                db.commit()
                return self._snapshot(db, completed, root, recursive, reused=True)
            report(0, 0, 'Resuming saved folder checkpoints…' if resumed else 'Updating persistent index…')
            while True:
                check_cancelled(cancelled)
                row = db.execute("SELECT path FROM folders WHERE generation=? AND status='pending' ORDER BY length(path),path LIMIT 1", (building,)).fetchone()
                if row is None:
                    break
                self._scan_folder(db, building, root, recursive, Path(row[0]), cancelled, report)
            check_cancelled(cancelled)
            # Revalidate folders/files changed during this pass before calling it complete.
            valid = self._validate(db, building, root, cancelled, report)
            errors = db.execute('SELECT count(*) FROM errors WHERE generation=?', (building,)).fetchone()[0]
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
            return self._snapshot(db, building, root, recursive, resumed=resumed, complete=complete)

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
