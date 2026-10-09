"""Directory scan scheduling, validation, and durable per-folder checkpoints."""
from contextlib import contextmanager, closing
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
from threading import RLock
from time import sleep, time, perf_counter

from ._directory_metadata import Entry, Snapshot, fingerprint
# Keep these long-standing imports available to existing consumers/instrumentation.
from ._directory_reader import SqlEntries, SqlDirectories, _entry
from .operations import check_cancelled, OperationCancelled
from ._directory_order import _sort_key, _encode_sort_parts
from .storage import cache_directory
from ._directory_totals import store_folder_stats
from ._directory_exclusions import scan_exclusions, is_excluded
from ._directory_schema import initialize_schema, ensure_folder, copy_entries, write_entries, delete_children, delete_entries, retire_generation


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
        self._session_checked = set()
        self._priority_folders = {}
        self._exclusion_checked = set()

    def invalidate(self, root=None):
        # Browser refresh runs on the GUI thread. Avoid waiting for a worker or DB.
        with self._state_lock:
            self._revision += 1
            self._invalidations[None if root is None else Path(root).absolute()] = self._revision

    def was_checked_this_session(self, root):
        """Cheap GUI-safe check; session state is shared by this cache's browsers."""
        with self._state_lock:
            return (self.database, Path(root).absolute()) in self._session_checked

    def set_priority_folders(self, owner, paths=()):
        """Register open views without touching SQLite or waiting for its writer.

        Each owner replaces its request on navigation and removes it on close.
        Scanners consult the current requests between folders, never mid-folder.
        """
        paths = tuple(Path(path).absolute() for path in paths)
        with self._state_lock:
            if paths:
                self._priority_folders[owner] = paths
            else:
                self._priority_folders.pop(owner, None)

    def _scan_blocked(self, folder):
        blocked = getattr(self, '_blocked_scan_folders', set())
        return folder in blocked or any(parent in blocked for parent in folder.parents)

    @staticmethod
    def _block_scan_tree(db, generation, folder):
        text = str(folder)
        prefix = text.rstrip(os.sep)+os.sep
        upper = prefix[:-1]+chr(ord(os.sep)+1)
        db.execute('INSERT OR IGNORE INTO scan_blocked VALUES(?)', (text,))
        db.execute('INSERT OR IGNORE INTO scan_blocked SELECT path FROM folders '
                   'WHERE generation=? AND path>=? AND path<?', (generation,prefix,upper))

    def _next_priority_folder(self, db, generation, root, handled, visited):
        with self._state_lock:
            targets = tuple(path for paths in self._priority_folders.values() for path in paths)
        for target in targets:
            if is_excluded(target, self._excluded_paths):
                continue
            if target in handled:
                continue
            if target != root and root not in target.parents:
                continue
            chain = [target]
            for ancestor in target.parents:
                if ancestor == root:
                    chain.append(root)
                    break
                if root not in ancestor.parents:
                    break
                chain.append(ancestor)
            # Missing ancestors must be discovered before the visible folder can
            # appear in the queue. Prioritize immediate contents, not its whole
            # subtree: once checked, normal discovery continues elsewhere.
            for folder in reversed(chain):
                if folder in visited or self._scan_blocked(folder):
                    continue
                if db.execute("SELECT 1 FROM folders WHERE generation=? AND path=? AND status='pending'",
                              (generation,str(folder))).fetchone():
                    return folder, folder == target
            handled.add(target)
        return None

    @contextmanager
    def _writer(self, cancelled, report=lambda done, total, message: None):
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
                        connection.set_progress_handler(lambda: int(cancelled()), 10_000)
                        self._schema(connection, cancelled, report)
                        yield connection
                    except OperationCancelled:
                        # Flush bounded pending work when cancellation arrives between folders.
                        connection.set_progress_handler(None,0)
                        connection.commit()
                        raise
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
    def _schema(db, cancelled=lambda: False, report=lambda done, total, message: None):
        """Compatibility entry point; schema ownership lives in _directory_schema."""
        initialize_schema(db, cancelled, report)

    @staticmethod
    def _folder_identity(folder, root):
        info = folder.stat() if folder == root else folder.lstat()
        if stat.S_ISLNK(info.st_mode) or (sys.platform=='win32' and folder!=root and folder.is_junction()):
            raise OSError('Directory became a link during scanning')
        if not stat.S_ISDIR(info.st_mode):
            raise NotADirectoryError(folder)
        return json.dumps(fingerprint(info))

    def _mark_totals_changed(self, folder, root):
        self._dirty_totals.add(folder)
        if folder == root or root not in folder.parents:
            return
        for parent in folder.parents:
            self._dirty_totals.add(parent)
            if parent == root:
                break

    def _publish_totals(self, db, generation, root, cancelled):
        started = perf_counter()
        try:
            if not db.execute('SELECT 1 FROM folder_totals WHERE generation=? LIMIT 1',(generation,)).fetchone():
                store_folder_stats(db,generation,root,cancelled)
            else:
                store_folder_stats(db,generation,root,cancelled,paths=self._dirty_totals)
            self._dirty_totals.clear()
        finally:
            self.last_metrics['aggregation_seconds'] += perf_counter()-started

    def _repair_exclusions(self, db, generation, root, cancelled, report):
        """Atomically remove previously cached excluded branches and fix ancestors.

        Indexed membership lookups keep subsequent calls cheap. Savepoint rollback
        prevents cancellation from publishing removed entries with stale totals.
        Other generations and existing SQLite readers retain their own membership.
        """
        affected = [path for path in self._excluded_paths if db.execute(
            'SELECT 1 FROM generation_entries g JOIN entry_nodes n ON n.id=g.node_id '
            'WHERE g.generation=? AND g.parent_id=(SELECT id FROM folder_paths WHERE path=?) AND n.name=? '
            'UNION ALL SELECT 1 FROM folders WHERE generation=? AND path=? LIMIT 1',
            (generation, str(path.parent), path.name, generation, str(path))).fetchone()]
        if not affected:
            return
        report(0, 0, 'Removing duplicate or excluded cached branches')
        dirty_before = self._dirty_totals.copy()
        db.execute('SAVEPOINT exclusion_repair')
        try:
            db.execute('CREATE TEMP TABLE IF NOT EXISTS exclusion_records(id INTEGER PRIMARY KEY)')
            db.execute('DELETE FROM exclusion_records')
            for path in affected:
                check_cancelled(cancelled)
                report(0, 0, f'Removing saved duplicate or excluded branch: {path}')
                prefix = str(path).rstrip(os.sep) + os.sep
                upper = prefix[:-1] + chr(ord(os.sep) + 1)
                db.execute('INSERT OR IGNORE INTO exclusion_records '
                           'SELECT record_id FROM generation_entries WHERE generation=? AND parent_id IN '
                           '(SELECT id FROM folder_paths WHERE path=? OR (path>=? AND path<?))',
                           (generation, str(path), prefix, upper))
                db.execute('INSERT OR IGNORE INTO exclusion_records '
                           'SELECT g.record_id FROM generation_entries g JOIN entry_nodes n ON n.id=g.node_id '
                           'WHERE g.generation=? AND g.parent_id=(SELECT id FROM folder_paths WHERE path=?) AND n.name=?',
                           (generation, str(path.parent), path.name))
                self._remove_tree(db, generation, str(path))
                db.execute('DELETE FROM generation_entries WHERE generation=? '
                           'AND parent_id=(SELECT id FROM folder_paths WHERE path=?) '
                           'AND node_id IN (SELECT id FROM entry_nodes WHERE parent_id='
                           '(SELECT id FROM folder_paths WHERE path=?) AND name=?)',
                           (generation, str(path.parent), str(path.parent), path.name))
                self._mark_totals_changed(path.parent, root)
            # Prune only touched, now-unreferenced metadata. Explicit Data scopes
            # may share these records and must retain them. No full-table vacuum.
            report(0, 0, 'Removing unused metadata from excluded branches')
            db.execute('CREATE TEMP TABLE IF NOT EXISTS exclusion_nodes(id INTEGER PRIMARY KEY)')
            db.execute('DELETE FROM exclusion_nodes')
            db.execute('INSERT OR IGNORE INTO exclusion_nodes SELECT node_id FROM entry_records '
                       'WHERE id IN (SELECT id FROM exclusion_records)')
            db.execute('DELETE FROM entry_records WHERE id IN (SELECT id FROM exclusion_records) '
                       'AND NOT EXISTS (SELECT 1 FROM generation_entries WHERE record_id=entry_records.id)')
            db.execute('DELETE FROM entry_nodes WHERE id IN (SELECT id FROM exclusion_nodes) '
                       'AND NOT EXISTS (SELECT 1 FROM entry_records WHERE node_id=entry_nodes.id)')
            db.execute('DELETE FROM exclusion_records')
            db.execute('DELETE FROM exclusion_nodes')
            report(0, 0, 'Recalculating saved sizes after exclusion cleanup')
            self._publish_totals(db, generation, root, cancelled)
            check_cancelled(cancelled)
            db.execute('RELEASE exclusion_repair')
        except BaseException:
            db.set_progress_handler(None, 0)
            # SQLite may already roll back the transaction when an interrupted
            # DELETE aborts. Preserve the original cancellation in that case.
            if db.in_transaction:
                db.execute('ROLLBACK TO exclusion_repair')
                db.execute('RELEASE exclusion_repair')
            self._dirty_totals = dirty_before
            raise

    def _checkpoint(self, db, cancelled, *, force=False):
        if force or cancelled() or self._checkpoint_entries>=4096 or time()-self._checkpoint_at>=.5:
            started = perf_counter()
            db.commit()
            self.last_metrics['checkpoint_seconds'] += perf_counter()-started
            self.last_metrics['checkpoints'] += 1
            self._checkpoint_entries = 0
            self._checkpoint_at = time()

    def _validate(self, db, generation, root, cancelled, report, *, root_only=False, check_files=True):
        started = perf_counter()
        try:
            return self._validate_impl(db,generation,root,cancelled,report,root_only=root_only,check_files=check_files)
        finally:
            self.last_metrics['validation_seconds'] += perf_counter()-started

    def _validate_impl(self, db, generation, root, cancelled, report, *, root_only=False, check_files=True):
        unchanged = True
        for (path,) in db.execute('SELECT path FROM errors WHERE generation=?', (generation,)).fetchall():
            db.execute("UPDATE folders SET status='pending' WHERE generation=? AND path=coalesce("
                       "(SELECT path FROM folders WHERE generation=? AND path=?),?)",
                       (generation, generation, path, str(Path(path).parent)))
        rows = db.execute('SELECT path,identity,status FROM folders WHERE generation=?' +
                          (' AND path=?' if root_only else '') + ' ORDER BY path',
                          (generation, str(root)) if root_only else (generation,))
        count = 0
        for text, expected, status in rows:
            check_cancelled(cancelled)
            if self._scan_blocked(Path(text)):
                unchanged = False
                continue
            valid = status == 'done'
            failed_path = text
            try:
                valid = valid and self._folder_identity(Path(text), root) == expected
                if valid and check_files:
                    children = db.execute('SELECT path,identity FROM entries WHERE generation=? AND parent=?', (generation, text))
                    for child, identity in children:
                        check_cancelled(cancelled)
                        self._checked_entries += 1
                        report(self._checked_entries, 0, f'Checking file metadata · {text}')
                        failed_path = child
                        if json.dumps(fingerprint(Path(child).lstat())) != identity:
                            valid = False
                            break
            except OSError as error:
                db.execute('INSERT OR REPLACE INTO errors VALUES(?,?,?)',
                           (generation, failed_path, str(error)))
                valid = False
            if not valid:
                self._mark_totals_changed(Path(text),root)
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
        upper = prefix[:-1] + chr(ord(os.sep)+1)
        for table in ('entries', 'folders', 'errors', 'folder_totals', 'folder_checks'):
            # The parent has already reconciled its entries. Preserve a new file
            # or link at the old directory's path while deleting its old children.
            if table == 'entries':
                if db.execute("SELECT 1 FROM sqlite_temp_master WHERE name='reconcile_records'").fetchone():
                    db.execute('INSERT OR IGNORE INTO reconcile_records '
                               'SELECT g.record_id FROM generation_entries g JOIN folder_paths f ON f.id=g.parent_id '
                               'WHERE g.generation=? AND (f.path=? OR (f.path>=? AND f.path<?))',
                               (generation,folder,prefix,upper))
                delete_entries(db, generation, scope=folder)
            else:
                db.execute(f'DELETE FROM {table} WHERE generation=? AND path=?',(generation,folder))
                db.execute(f'DELETE FROM {table} WHERE generation=? AND path>=? AND path<?',
                           (generation,prefix,upper))

    def _scan_folder(self, db, generation, root, recursive, folder, cancelled, report, *, checkpoint=True):
        text = str(folder)
        parent_id = ensure_folder(db, folder)
        prefix = text.rstrip(os.sep)+os.sep
        upper = prefix[:-1]+chr(ord(os.sep)+1)
        db.execute('DELETE FROM errors WHERE generation=? AND path=?',(generation,text))
        db.execute('DELETE FROM errors WHERE generation=? AND path>=? AND path<? AND instr(substr(path,?),?)=0 '
                   'AND NOT EXISTS (SELECT 1 FROM folders f WHERE f.generation=errors.generation AND f.path=errors.path)',
                   (generation,prefix,upper,len(prefix)+1,os.sep))
        if not checkpoint:
            db.execute('INSERT OR IGNORE INTO reconcile_records SELECT record_id FROM generation_entries '
                       'WHERE generation=? AND parent_id=?', (generation,parent_id))
        delete_children(db, generation, folder)
        seen = set()
        count = 0
        entry_rows, folder_rows = [], []
        def flush():
            if not entry_rows:
                return
            # A cancelled scan still saves its last bounded metadata batch.
            db.set_progress_handler(None,0)
            started = perf_counter()
            try:
                write_entries(db, generation, parent_id, entry_rows)
                db.executemany("INSERT INTO folders VALUES(?,?,?,'pending',NULL) ON CONFLICT(generation,path) "
                               "DO UPDATE SET status=CASE WHEN folders.identity=? AND folders.status='done' "
                               "THEN 'done' ELSE 'pending' END",folder_rows)
                self._checkpoint_entries += len(entry_rows)
                entry_rows.clear();folder_rows.clear()
            finally:
                self.last_metrics['database_write_seconds'] += perf_counter()-started
                db.set_progress_handler(lambda:int(cancelled()),10000)
        try:
            before = self._folder_identity(folder, root)
            with os.scandir(folder) as children:
                for child in children:
                    check_cancelled(cancelled)
                    path = Path(child.path)
                    if is_excluded(path, self._excluded_paths):
                        continue
                    try:
                        started = perf_counter()
                        info = child.stat(follow_symlinks=False)
                        self.last_metrics['metadata_seconds'] += perf_counter()-started
                        link = stat.S_ISLNK(info.st_mode) or (sys.platform=='win32' and path.is_junction())
                        directory = not link and stat.S_ISDIR(info.st_mode)
                        identity = json.dumps(fingerprint(info))
                        entry_rows.append((path.name, path.name.casefold(), directory,
                                           0 if directory or link else info.st_size, info.st_mtime_ns,
                                           link, identity, _sort_key(path.name)[1:]))
                        if directory and recursive:
                            seen.add(str(path))
                            folder_rows.append((generation,str(path),text,identity))
                    except OSError as error:
                        db.execute('INSERT OR REPLACE INTO errors VALUES(?,?,?)', (generation, str(path), str(error)))
                    count += 1
                    self._discovered_entries += 1
                    if count % 512 == 0:
                        flush()
                        if checkpoint:
                            self._checkpoint(db,cancelled)
                    report(self._discovered_entries, 0, f'Indexing {folder}')
            flush()
            for (old,) in db.execute('SELECT path FROM folders WHERE generation=? AND parent=?', (generation, text)).fetchall():
                if old not in seen:
                    self._remove_tree(db, generation, old)
            # Changes during enumeration require another pass rather than publishing a stale folder.
            after = self._folder_identity(folder, root)
            db.execute('UPDATE folders SET status=?,identity=? WHERE generation=? AND path=?',
                       ('done' if before == after else 'pending', after, generation, text))
        except OSError as error:
            if db.execute("SELECT 1 FROM sqlite_temp_master WHERE name='scan_blocked'").fetchone():
                self._blocked_scan_folders.add(folder)
                self._block_scan_tree(db, generation, folder)
            db.execute('INSERT OR REPLACE INTO errors VALUES(?,?,?)', (generation, text, str(error)))
            db.execute("UPDATE folders SET status='error' WHERE generation=? AND path=?", (generation, text))
        finally:
            # Preserve partial metadata; the folder stays pending until enumeration finishes.
            flush()
            self._mark_totals_changed(folder,root)
            if checkpoint:
                self._checkpoint(db,cancelled)
            if checkpoint and not cancelled() and time() - self._totals_last > self._totals_interval:
                started = time()
                self._publish_totals(db,generation,root,cancelled)
                self._checkpoint(db,cancelled,force=True)
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
        has_totals = db.execute("SELECT 1 FROM sqlite_master WHERE name='folder_totals'").fetchone()
        total = db.execute('SELECT complete FROM folder_totals WHERE generation=? AND path=?',
                           (generation, str(root))).fetchone() if has_totals else None
        complete = complete and (total is None or bool(total[0]))
        return Snapshot(root, recursive, entries, errors, scanned or time(), directories=directories, reused=reused,
                        validated_at=time(), resumed=resumed, complete=complete, metadata_checked=metadata_checked)

    def _seed_descendants(self, db, generation, root, cancelled, report):
        """Merge overlapping saved branches, preferring their most specific checkpoint."""
        sources = db.execute('SELECT root,coalesce(building,completed) FROM roots '
                             'WHERE recursive=1 AND root!=? AND (building IS NOT NULL OR completed IS NOT NULL) '
                             'ORDER BY length(root) DESC,root', (str(root),)).fetchall()
        covered = []
        for source_text, source in sources:
            check_cancelled(cancelled)
            branch = Path(source_text)
            if root not in branch.parents or is_excluded(branch, self._excluded_paths):
                continue
            report(0, 0, f'Reusing saved branch {branch}')
            folder_exclusions, parameters, excluded_branches = [], [], []
            for nested in covered:
                if branch not in nested.parents:
                    continue
                prefix = str(nested).rstrip(os.sep) + os.sep
                upper = prefix[:-1] + chr(ord(os.sep) + 1)
                excluded_branches.append(nested)
                folder_exclusions.append('NOT (path=? OR (path>=? AND path<?))')
                parameters.append((str(nested),prefix,upper))
            folder_where = ''.join(' AND '+clause for clause in folder_exclusions)
            folder_args = tuple(value for group in parameters for value in group)
            prefix = source_text.rstrip(os.sep) + os.sep
            upper = prefix[:-1] + chr(ord(os.sep) + 1)
            delete_entries(db, generation, scope=branch, exclude=excluded_branches)
            for table in ('folders','errors'):
                db.execute(f'DELETE FROM {table} WHERE generation=? AND (path=? OR (path>=? AND path<?))'+folder_where,
                           (generation,source_text,prefix,upper)+folder_args)
            copy_entries(db, generation, source, exclude=excluded_branches)
            db.execute('INSERT OR IGNORE INTO folders SELECT ?,path,CASE WHEN path=? THEN ? ELSE parent END,status,identity '
                       'FROM folders WHERE generation=?'+folder_where, (generation, source_text, str(branch.parent), source)+folder_args)
            db.execute('INSERT OR IGNORE INTO errors SELECT ?,path,error FROM errors WHERE generation=?'+folder_where,
                       (generation, source)+folder_args)
            # Link separately indexed deep branches into the new root's queue.
            # Parent enumeration can then remove a branch that no longer exists.
            for ancestor in branch.parents:
                if ancestor == root:
                    break
                db.execute("INSERT OR IGNORE INTO folders VALUES(?,?,?,'pending',NULL)",
                           (generation,str(ancestor),str(ancestor.parent)))
            covered.append(branch)
        return bool(covered)

    def get(self, root, recursive=True, *, refresh=False, cancelled=lambda: False,
            report=lambda done, total, message: None, validate_files=True, reuse_for=0, retry_errors=True):
        root = Path(root).absolute()
        if not root.is_dir():
            raise NotADirectoryError(root)
        if root.resolve() == self.database.parent.resolve():
            raise ValueError('The directory index storage folder cannot index itself. Choose another folder.')
        report(0, 0, 'Waiting for index writer…')
        with self._writer(cancelled, report) as db:
            self._discovered_entries = self._checked_entries = 0
            self._blocked_scan_folders = set()
            self._dirty_totals = set()
            self._checkpoint_entries = 0
            self._checkpoint_at = time()
            self.last_metrics = dict(metadata_seconds=0.,database_write_seconds=0.,aggregation_seconds=0.,validation_seconds=0.,checkpoint_seconds=0.,checkpoints=0)
            self._totals_interval = 2
            with self._state_lock:
                revision = self._revision
                checked_revision = self._validated_roots.get((root, recursive), 0)
                dirty = any(mark > checked_revision and (path is None or path == root or path in root.parents or root in path.parents)
                            for path, mark in self._invalidations.items())
            self._totals_last = time()
            self._excluded_paths = scan_exclusions(root, self.database)
            db.execute('INSERT OR IGNORE INTO roots(root,recursive) VALUES(?,?)', (str(root), recursive))
            completed, building = db.execute('SELECT completed,building FROM roots WHERE root=? AND recursive=?', (str(root), recursive)).fetchone()
            for generation in (completed, building):
                if generation:
                    self._repair_exclusions(db, generation, root, cancelled, report)
            db.commit()
            if recursive and not completed and not building and not refresh and reuse_for:
                # Navigation can read a freshly validated ancestor directly; no work
                # generation, metadata pass or duplicate subtree rows are needed.
                ancestors = tuple(str(path) for path in root.parents)
                if ancestors:
                    candidates = db.execute('SELECT root,completed FROM roots WHERE recursive=1 AND building IS NULL '
                                            'AND completed IS NOT NULL AND root IN ('+', '.join('?' for _ in ancestors)+') '
                                            'ORDER BY length(root) DESC',ancestors).fetchall()
                    for source_text,source in candidates:
                        source_root = Path(source_text)
                        with self._state_lock:
                            stamp = self._validated_times.get((source_root,True),0)
                            checked = self._validated_roots.get((source_root,True),0)
                            changed = any(mark>checked and (path is None or path==root or path in root.parents or root in path.parents)
                                          for path,mark in self._invalidations.items())
                            fresh = time()-stamp<reuse_for and not changed
                        if fresh:
                            report(0,0,'Using recently checked ancestor index…')
                            return self._snapshot(db,source,root,True,reused=True,scope=root,cancelled=cancelled)
            if recursive and not completed and not building and not refresh:
                # Seed a newly browsed subtree from completed or partial ancestor checkpoints.
                # Validation still checks every descendant before reuse, but names
                # and unchanged folders need no second filesystem enumeration.
                ancestors = tuple(str(path) for path in root.parents)
                if ancestors:
                    covering = db.execute('SELECT coalesce(building,completed),building IS NOT NULL FROM roots '
                                          'WHERE recursive=1 AND (completed IS NOT NULL OR building IS NOT NULL) '
                                          'AND root IN (' + ','.join('?' for _ in ancestors) + ') ORDER BY length(root) DESC LIMIT 1', ancestors).fetchone()
                    if covering:
                        report(0, 0, 'Reusing saved subtree checkpoints…')
                        seed = db.execute('INSERT INTO scans(root,recursive,scanned_at) '
                                          'SELECT ?,1,scanned_at FROM scans WHERE id=?', (str(root), covering[0])).lastrowid
                        prefix = str(root).rstrip(os.sep) + os.sep
                        upper = prefix[:-1] + chr(ord(os.sep) + 1)
                        copy_entries(db, seed, covering[0], scope=root)
                        db.execute('INSERT INTO folders SELECT ?,path,parent,status,identity FROM folders WHERE generation=? '
                                   'AND (path=? OR (path>=? AND path<?))', (seed, covering[0], str(root), prefix, upper))
                        db.execute('INSERT INTO errors SELECT ?,path,error FROM errors WHERE generation=? '
                                   'AND (path=? OR (path>=? AND path<?))', (seed, covering[0], str(root), prefix, upper))
                        if not db.execute('SELECT 1 FROM folders WHERE generation=? AND path=?', (seed, str(root))).fetchone():
                            db.execute("INSERT INTO folders VALUES(?,?,?,'pending',NULL)", (seed, str(root), ''))
                        imported = self._seed_descendants(db, seed, root, cancelled, report)
                        self._repair_exclusions(db, seed, root, cancelled, report)
                        if covering[1] or imported:
                            building = seed
                            db.execute('UPDATE roots SET building=? WHERE root=? AND recursive=1', (seed, str(root)))
                        else:
                            completed = seed
                            db.execute('UPDATE roots SET completed=? WHERE root=? AND recursive=1', (seed, str(root)))
                        if imported:
                            store_folder_stats(db, seed, root, cancelled)
                        db.commit()
                        if imported:
                            report(0, 0, 'Saved progressive folder totals')
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
                retire_generation(db, building)
                building = None
            # Validate on disk using one folder at a time. A completed generation is
            # immutable for readers, so validation/status changes happen in a work copy.
            if not building:
                building = db.execute('INSERT INTO scans(root,recursive) VALUES(?,?)', (str(root), recursive)).lastrowid
                if completed and not refresh:
                    copy_entries(db, building, completed)
                    db.execute('INSERT INTO folders SELECT ?,path,parent,status,identity FROM folders WHERE generation=?', (building, completed))
                    db.execute('INSERT INTO folder_totals SELECT ?,path,size,files,folders,skipped,extensions,complete,scanned_at FROM folder_totals WHERE generation=?',(building,completed))
                else:
                    db.execute("INSERT INTO folders VALUES(?,?,?,'pending',NULL)", (building, str(root), ''))
                db.execute('UPDATE roots SET building=? WHERE root=? AND recursive=?', (building, str(root), recursive))
                if recursive and not completed and not refresh:
                    # A new higher starting point can reuse independently indexed branches.
                    # Prefer more specific checkpoints when cached scopes overlap.
                    covered = self._seed_descendants(db, building, root, cancelled, report)
                    self._repair_exclusions(db, building, root, cancelled, report)
                    if covered:
                        resumed = True
                        store_folder_stats(db, building, root, cancelled)
                db.commit()
                if resumed:
                    report(0, 0, 'Saved progressive folder totals')
            db.execute('CREATE TEMP TABLE scan_blocked(path TEXT PRIMARY KEY)')
            if not retry_errors:
                # Saved directory failures require explicit retry. Missing work
                # from cancellation remains eligible for normal resume.
                self._blocked_scan_folders = {Path(path) for (path,) in db.execute(
                    'SELECT f.path FROM folders f JOIN errors e ON e.generation=f.generation AND e.path=f.path '
                    'WHERE f.generation=?', (building,))}
                for folder in self._blocked_scan_folders:
                    self._block_scan_tree(db, building, folder)
            # Finish discovering missing branches before rechecking old metadata.
            # Completed folders are validated after discovery, including on resume.
            unchanged = False
            if not resumed and completed:
                unchanged = self._validate(db, building, root, cancelled, report)
            if unchanged and completed and not resumed and not dirty and not refresh:
                db.execute('UPDATE roots SET building=NULL WHERE root=? AND recursive=?', (str(root), recursive))
                retire_generation(db, building)
                db.commit()
                return self._snapshot(db, completed, root, recursive, reused=True, cancelled=cancelled)
            report(0, 0, 'Resuming saved folder checkpoints…' if resumed else 'Updating persistent index…')
            def discover_pending():
                # A live directory may change on every enumeration. Give each
                # folder one attempt per pass; retain unstable checkpoints for
                # explicit retry instead of feeding them back forever.
                db.execute('CREATE TEMP TABLE IF NOT EXISTS scan_visited(path TEXT PRIMARY KEY)')
                db.execute('DELETE FROM scan_visited')
                handled_priorities, visited_priorities = set(), set()
                attempted = 0
                while True:
                    check_cancelled(cancelled)
                    # Batches avoid sorting the whole pending tree for every folder.
                    rows = db.execute("SELECT path FROM folders WHERE generation=? AND status='pending' AND identity IS NULL AND path NOT IN (SELECT path FROM scan_visited) AND path NOT IN (SELECT path FROM scan_blocked) ORDER BY length(path),path LIMIT 256", (building,)).fetchall()
                    if not rows:
                        rows = db.execute("SELECT path FROM folders WHERE generation=? AND status='pending' AND path NOT IN (SELECT path FROM scan_visited) AND path NOT IN (SELECT path FROM scan_blocked) ORDER BY length(path),path LIMIT 256", (building,)).fetchall()
                    if not rows:
                        break
                    for (path,) in rows:
                        check_cancelled(cancelled)
                        while priority := self._next_priority_folder(db, building, root, handled_priorities, visited_priorities):
                            check_cancelled(cancelled)
                            folder, visible = priority
                            visited_priorities.add(folder)
                            db.execute('INSERT OR IGNORE INTO scan_visited VALUES(?)', (str(folder),))
                            self._scan_folder(db, building, root, recursive, folder, cancelled, report)
                            attempted += 1
                            # Publish a visible folder promptly even during a long
                            # first scan, without changing its original scan root.
                            if visible:
                                self._publish_totals(db, building, root, cancelled)
                                self._checkpoint(db, cancelled, force=True)
                                report(0, 0, 'Saved progressive folder totals')
                        # A parent reconciliation can remove a previously queued child.
                        if db.execute("SELECT 1 FROM folders WHERE generation=? AND path=? AND status='pending' AND path NOT IN (SELECT path FROM scan_visited) AND path NOT IN (SELECT path FROM scan_blocked)", (building, path)).fetchone():
                            db.execute('INSERT OR IGNORE INTO scan_visited VALUES(?)', (path,))
                            self._scan_folder(db, building, root, recursive, Path(path), cancelled, report)
                            attempted += 1
                return attempted
            discover_pending()
            check_cancelled(cancelled)
            valid = self._validate(db, building, root, cancelled, report)
            if resumed and not valid:
                # Only a failed verification needs a repair pass and recheck.
                repaired = discover_pending()
                if repaired:
                    valid = self._validate(db, building, root, cancelled, report)
            errors = db.execute('SELECT count(*) FROM errors WHERE generation=?', (building,)).fetchone()[0]
            self._publish_totals(db,building,root,cancelled)
            db.execute('INSERT OR REPLACE INTO folder_checks VALUES(?,?,?)', (building, str(root), time()))
            db.execute('UPDATE scans SET scanned_at=? WHERE id=?', (time(), building))
            complete = valid and not errors
            with self._state_lock:
                visible_roots = tuple(path for paths in self._priority_folders.values() for path in paths)
            checked = [path for path in visible_roots if (path == root or root in path.parents) and
                           db.execute("SELECT 1 FROM folders WHERE generation=? AND path=?",
                                      (building,str(path))).fetchone()]
            if complete:
                db.execute('UPDATE roots SET completed=?,building=NULL WHERE root=? AND recursive=?', (building, str(root), recursive))
                if completed:
                    retire_generation(db, completed)
            db.commit()
            with self._state_lock:
                # A finished attempt is terminal even when some folders were
                # unreadable/unstable. Cancellation never reaches this point.
                self._session_checked.update((self.database,path) for path in (root,*checked))
                if revision == self._revision and complete:
                    self._validated_roots[(root, recursive)] = revision
                    self._validated_times[(root, recursive)] = time()
            return self._snapshot(db, building, root, recursive, resumed=resumed, complete=complete, cancelled=cancelled)

    def reconcile_folder(self, root, *, changes=(), full=False, once=False, cancelled=lambda: False,
                         report=lambda done, total, message: None, recursive_initial=True):
        """Check visible contents; completed caches update atomically without tree-wide validation.

        With full=True, also check every saved descendant for explicit Refresh.
        With once=True, revisits reuse saved contents after this session's first
        finished attempt; notifications/explicit changes bypass that shortcut.
        Missing or interrupted indices retain the established resumable full scan.
        Existing readers keep their SQLite transaction while changed rows and parent
        aggregates are updated in the same generation, without copying the tree.
        """
        root = Path(root).absolute()
        changes = tuple(changes)
        if not recursive_initial and not full:
            # Navigation may request only visible contents. Never seed/copy a
            # whole cached subtree or resume its pending descendants here.
            snapshot = self.get(root, recursive=False, cancelled=cancelled, report=report)
            with self._state_lock:
                self._session_checked.add((self.database, root))
            return snapshot
        if once and not full and not changes and self.was_checked_this_session(root):
            snapshot = self.peek(root, cancelled=cancelled)
            if snapshot is not None:
                report(0, 0, 'Reusing saved index')
                return snapshot
        from ._directory_reconcile import reconcile_existing
        snapshot = reconcile_existing(self, root, changes, cancelled, report, full=full,
                                      allow_partial=not full and self.was_checked_this_session(root))
        if snapshot is None:
            snapshot = self.get(root, cancelled=cancelled, report=report, retry_errors=full)
        if snapshot.complete:
            with self._state_lock:
                self._session_checked.add((self.database, root))
        return snapshot

    def repair_cached_exclusions(self, root, *, cancelled=lambda: False,
                                 report=lambda done, total, message: None):
        """Repair saved macOS root aliases without resuming or validating a scan.

        Cache-first applications call this on their index worker before peek().
        Ordinary peek() remains read-only. Independent Data scopes are retained.
        """
        root = Path(root).absolute()
        from ._directory_exclusions import MACOS_DATA
        exclusions = scan_exclusions(root, self.database)
        if MACOS_DATA not in exclusions or not self.database.is_file():
            return
        with self._state_lock:
            if root in self._exclusion_checked:
                return
        with self._writer(cancelled, report) as db:
            self._excluded_paths = exclusions
            self._dirty_totals = set()
            self.last_metrics = dict(metadata_seconds=0., database_write_seconds=0., aggregation_seconds=0.,
                                     validation_seconds=0., checkpoint_seconds=0., checkpoints=0)
            rows = db.execute('SELECT completed,building FROM roots WHERE root=?', (str(root),)).fetchall()
            for generation in {value for row in rows for value in row if value is not None}:
                check_cancelled(cancelled)
                self._repair_exclusions(db, generation, root, cancelled, report)
            db.commit()
        with self._state_lock:
            self._exclusion_checked.add(root)

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
            if (row is None or not (row[1] or row[2])) and recursive:
                ancestors = tuple(str(path) for path in root.parents)
                if ancestors:
                    row = db.execute('SELECT root,completed,building FROM roots WHERE recursive=1 AND root IN (' +
                                     ','.join('?' for _ in ancestors) + ') AND (completed IS NOT NULL OR building IS NOT NULL) '
                                     'ORDER BY length(root) DESC LIMIT 1', ancestors).fetchone()
                if row is None:
                    row = db.execute('SELECT root,completed,building FROM roots WHERE root=? AND recursive=0', (str(root),)).fetchone()
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

    def index_issues(self, root, *, limit=500, cancelled=lambda: False):
        """Read scoped diagnostic rows without scanning files or taking a writer lock.

        Query on a worker. Counts cover all recorded issues; returned paths are
        bounded to limit. Pending checkpoints distinguish unfinished enumeration
        from folders requiring verification, while recorded errors retain details.
        """
        if limit < 1:
            raise ValueError('limit must be positive')
        root = Path(root).absolute()
        empty = {'rows': (), 'counts': {}, 'total': 0, 'partial': False}
        if not self.database.is_file():
            return empty
        with closing(sqlite3.connect(f'{self.database.as_uri()}?mode=ro', uri=True)) as db:
            db.set_progress_handler(lambda: int(cancelled()), 1000)
            check_cancelled(cancelled)
            db.execute('BEGIN')
            ancestors = (str(root),) + tuple(str(path) for path in root.parents)
            row = db.execute('SELECT completed,building FROM roots WHERE recursive=1 AND root IN (' +
                             ','.join('?' for _ in ancestors) + ') AND (completed IS NOT NULL OR building IS NOT NULL) '
                             'ORDER BY length(root) DESC LIMIT 1', ancestors).fetchone()
            if row is None:
                return empty
            generation = row[1] or row[0]
            prefix = str(root).rstrip(os.sep) + os.sep
            upper = prefix[:-1] + chr(ord(os.sep) + 1)
            query = ("SELECT path,'Scan error' AS kind,error AS reason FROM errors "
                     "WHERE generation=? AND (path=? OR (path>=? AND path<?)) UNION ALL "
                     "SELECT f.path,CASE WHEN f.identity IS NULL THEN 'Not fully scanned' ELSE 'Needs recheck' END,"
                     "CASE WHEN f.identity IS NULL THEN 'New or interrupted folder; enumeration unfinished' "
                     "ELSE 'Folder changed during scanning or metadata verification did not finish' END "
                     "FROM folders f WHERE f.generation=? AND f.status!='done' "
                     "AND (f.path=? OR (f.path>=? AND f.path<?)) "
                     "AND NOT EXISTS (SELECT 1 FROM errors e WHERE e.generation=f.generation AND e.path=f.path)")
            params = (generation, str(root), prefix, upper) * 2
            counts = dict(db.execute('SELECT kind,count(*) FROM (' + query + ') GROUP BY kind', params))
            rows = tuple((Path(path), kind, reason) for path, kind, reason in db.execute(
                'SELECT * FROM (' + query + ") ORDER BY CASE kind WHEN 'Scan error' THEN 0 ELSE 1 END,path LIMIT ?", params + (limit,)))
            check_cancelled(cancelled)
            return {'rows': rows, 'counts': counts, 'total': sum(counts.values()), 'partial': row[1] is not None}

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
            table = 'generation_entries' if db.execute('PRAGMA user_version').fetchone()[0] >= 3 else 'entries'
            entries = db.execute(f'SELECT count(*) FROM {table} WHERE generation=?', (generation,)).fetchone()[0]
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
                            retire_generation(db, generation)
            check_cancelled(cancelled)
            if not db.execute('SELECT 1 FROM generation_entries LIMIT 1').fetchone():
                db.execute('DELETE FROM entry_nodes')
                db.execute('DELETE FROM folder_paths')
            db.commit()
            with self._state_lock:
                self._session_checked.clear()
                self._exclusion_checked.clear()
