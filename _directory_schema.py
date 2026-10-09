"""Compact directory-index records and transactional upgrades.

Folder addresses are cached once for indexed lookups. File names and immutable
metadata are shared between all generations; generations contain integer links.
The entries view preserves the existing internal SQL row contract and public Path
API. A pre-upgrade SQLite backup includes committed WAL data and is never replaced.
"""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from ._directory_order import _sort_key
from .operations import check_cancelled

SCHEMA_VERSION = 3


def ensure_folder(db, path):
    """Intern a lexical folder hierarchy without recursion or resolving symlinks."""
    missing = []
    current = Path(path)
    parent_id = None
    while True:
        row = db.execute('SELECT id FROM folder_paths WHERE path=?', (str(current),)).fetchone()
        if row:
            parent_id = row[0]
            break
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for folder in reversed(missing):
        text = str(folder)
        parent_id = db.execute('INSERT INTO folder_paths(parent_id,name,path,sort_prefix) VALUES(?,?,?,?)',
            (parent_id, folder.name or text, text, _sort_key(text.rstrip(os.sep) + os.sep)[:-1])).lastrowid
    return parent_id


def _backup(db, cancelled):
    filename = db.execute('PRAGMA database_list').fetchone()[2]
    if not filename:
        return
    target = Path(filename).with_suffix('.pre-v3.sqlite3')
    if target.exists():
        return
    # Backup first, outside the migration transaction; staging avoids retaining an
    # incomplete recovery file after a disk-full error or interrupted process.
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(dir=target.parent, prefix='.index-upgrade-', delete=False) as stream:
        staged = Path(stream.name)
    try:
        with closing(sqlite3.connect(staged)) as recovery:
            db.backup(recovery, pages=256, progress=lambda *args: check_cancelled(cancelled))
            if recovery.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Directory-index recovery copy failed its integrity check')
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)


def ensure_reader_view(db):
    """Expose integer IDs for scoped readers without changing the old row view."""
    separator = os.sep.replace("'", "''")
    db.execute(f'''CREATE VIEW IF NOT EXISTS indexed_entries AS
        SELECT g.parent_id,g.node_id,g.record_id,g.generation,
               rtrim(f.path,'{separator}')||'{separator}'||n.name AS path,
               f.path AS parent,n.name_fold,r.directory,r.size,r.modified,r.symlink,r.identity,
               CAST(f.sort_prefix||n.sort_key AS BLOB) AS sort_key
        FROM generation_entries g JOIN entry_nodes n ON n.id=g.node_id
        JOIN folder_paths f ON f.id=g.parent_id JOIN entry_records r ON r.id=g.record_id''')


def upgrade_entries(db, cancelled=lambda: False):
    """Replace repeated entry rows atomically; keep saved generations/checkpoints."""
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version not in (0, 1, 2):
        raise RuntimeError(f'Unsupported directory index version {version}')
    if version:
        _backup(db, cancelled)
    check_cancelled(cancelled)
    separator = os.sep.replace("'", "''")
    try:
        db.executescript('''BEGIN IMMEDIATE;
            ALTER TABLE entries RENAME TO legacy_entries;
            DROP INDEX IF EXISTS entry_parent;
            DROP INDEX IF EXISTS entry_order;
            DROP INDEX IF EXISTS entry_name_order;
            CREATE TABLE folder_paths(
                id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES folder_paths(id),
                name TEXT NOT NULL, path TEXT NOT NULL UNIQUE, sort_prefix BLOB NOT NULL);
            CREATE INDEX folder_path_parent ON folder_paths(parent_id);
            CREATE TABLE entry_nodes(
                id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL REFERENCES folder_paths(id),
                name TEXT NOT NULL, name_fold TEXT NOT NULL, sort_key BLOB NOT NULL,
                UNIQUE(parent_id,name));
            CREATE TABLE entry_records(
                id INTEGER PRIMARY KEY, node_id INTEGER NOT NULL REFERENCES entry_nodes(id),
                directory INTEGER NOT NULL, size INTEGER NOT NULL, modified INTEGER NOT NULL,
                symlink INTEGER NOT NULL, identity TEXT NOT NULL,
                UNIQUE(node_id,directory,size,modified,symlink,identity));
            CREATE TABLE generation_entries(
                generation INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                parent_id INTEGER NOT NULL REFERENCES folder_paths(id),
                node_id INTEGER NOT NULL REFERENCES entry_nodes(id),
                record_id INTEGER NOT NULL REFERENCES entry_records(id),
                PRIMARY KEY(generation,parent_id,node_id));
            CREATE INDEX generation_record ON generation_entries(record_id);
        ''')
        # Only folder-sized work constructs Path objects. Huge file sets migrate
        # through SQL; their full paths never enter the new persistent tables.
        for (parent,) in db.execute('SELECT DISTINCT parent FROM legacy_entries').fetchall():
            check_cancelled(cancelled)
            ensure_folder(db, parent)
        for (folder,) in db.execute('SELECT DISTINCT path FROM folders').fetchall():
            check_cancelled(cancelled)
            ensure_folder(db, folder)
        db.execute("INSERT OR IGNORE INTO entry_nodes(parent_id,name,name_fold,sort_key) "
                   "SELECT f.id,substr(e.path,length(rtrim(e.parent,?))+2),e.name_fold,substr(e.sort_key,length(f.sort_prefix)+1) "
                   "FROM legacy_entries e JOIN folder_paths f ON f.path=e.parent", (os.sep,))
        db.execute('INSERT OR IGNORE INTO entry_records(node_id,directory,size,modified,symlink,identity) '
                   'SELECT n.id,e.directory,e.size,e.modified,e.symlink,e.identity '
                   'FROM legacy_entries e JOIN folder_paths f ON f.path=e.parent '
                   'JOIN entry_nodes n ON n.parent_id=f.id AND n.name_fold=e.name_fold '
                   'AND n.name=substr(e.path,length(rtrim(e.parent,?))+2)', (os.sep,))
        db.execute('INSERT INTO generation_entries SELECT e.generation,f.id,n.id,r.id '
                   'FROM legacy_entries e JOIN folder_paths f ON f.path=e.parent '
                   'JOIN entry_nodes n ON n.parent_id=f.id AND n.name=substr(e.path,length(rtrim(e.parent,?))+2) '
                   'JOIN entry_records r ON r.node_id=n.id AND r.directory=e.directory AND r.size=e.size '
                   'AND r.modified=e.modified AND r.symlink=e.symlink AND r.identity=e.identity', (os.sep,))
        before = db.execute('SELECT count(*) FROM legacy_entries').fetchone()[0]
        after = db.execute('SELECT count(*) FROM generation_entries').fetchone()[0]
        if before != after:
            raise RuntimeError('Directory index upgrade entry count mismatch')
        db.execute('DROP TABLE legacy_entries')
        # execute rather than executescript: the entire upgrade remains atomic.
        db.execute(f'''CREATE VIEW entries AS
            SELECT g.generation,rtrim(f.path,'{separator}')||'{separator}'||n.name AS path,
                   f.path AS parent,n.name_fold,r.directory,r.size,r.modified,r.symlink,r.identity,CAST(f.sort_prefix||n.sort_key AS BLOB) AS sort_key
            FROM generation_entries g JOIN entry_nodes n ON n.id=g.node_id
            JOIN folder_paths f ON f.id=g.parent_id JOIN entry_records r ON r.id=g.record_id''')
        db.execute(f'''CREATE TRIGGER entries_insert INSTEAD OF INSERT ON entries BEGIN
            INSERT OR IGNORE INTO entry_nodes(parent_id,name,name_fold,sort_key)
                SELECT id,substr(NEW.path,length(rtrim(NEW.parent,'{separator}'))+2),NEW.name_fold,substr(NEW.sort_key,length(sort_prefix)+1)
                FROM folder_paths WHERE path=NEW.parent;
            INSERT OR IGNORE INTO entry_records(node_id,directory,size,modified,symlink,identity)
                SELECT n.id,NEW.directory,NEW.size,NEW.modified,NEW.symlink,NEW.identity
                FROM entry_nodes n JOIN folder_paths f ON f.id=n.parent_id
                WHERE f.path=NEW.parent AND n.name=substr(NEW.path,length(rtrim(NEW.parent,'{separator}'))+2);
            INSERT OR REPLACE INTO generation_entries(generation,parent_id,node_id,record_id)
                SELECT NEW.generation,f.id,n.id,r.id FROM entry_nodes n
                JOIN folder_paths f ON f.id=n.parent_id JOIN entry_records r ON r.node_id=n.id
                WHERE f.path=NEW.parent AND n.name=substr(NEW.path,length(rtrim(NEW.parent,'{separator}'))+2)
                  AND r.directory=NEW.directory AND r.size=NEW.size AND r.modified=NEW.modified
                  AND r.symlink=NEW.symlink AND r.identity=NEW.identity;
        END''')
        db.execute(f'''CREATE TRIGGER entries_delete INSTEAD OF DELETE ON entries BEGIN
            DELETE FROM generation_entries WHERE generation=OLD.generation
                AND parent_id=(SELECT id FROM folder_paths WHERE path=OLD.parent) AND node_id=(
                SELECT n.id FROM entry_nodes n JOIN folder_paths f ON f.id=n.parent_id
                WHERE f.path=OLD.parent AND n.name=substr(OLD.path,length(rtrim(OLD.parent,'{separator}'))+2));
        END''')
        check_cancelled(cancelled)
        ensure_reader_view(db)
        db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        db.commit()
    except BaseException:
        # Rollback must remain possible after the progress handler interrupted SQL.
        db.set_progress_handler(None, 0)
        db.rollback()
        raise


def _membership_scope(scope, exclude):
    """Translate subtree boundaries to indexed folder IDs, without file-path joins."""
    clauses, parameters = [], []
    for path, excluded in ([(scope, False)] if scope is not None else []) + [(path, True) for path in exclude]:
        text = str(path)
        prefix = text.rstrip(os.sep) + os.sep
        upper = prefix[:-1] + chr(ord(os.sep) + 1)
        operator = 'NOT IN' if excluded else 'IN'
        clauses.append(f' AND parent_id {operator} (SELECT id FROM folder_paths '
                       'WHERE path=? OR (path>=? AND path<?))')
        parameters.extend((text, prefix, upper))
    return ''.join(clauses), tuple(parameters)


def copy_entries(db, target, source, *, scope=None, exclude=()):
    """Share immutable records with a new generation, respecting deeper checkpoints."""
    clause, parameters = _membership_scope(scope, exclude)
    db.execute('INSERT OR REPLACE INTO generation_entries '
               'SELECT ?,parent_id,node_id,record_id FROM generation_entries WHERE generation=?' + clause,
               (target, source) + parameters)


def delete_entries(db, generation, *, scope=None, exclude=()):
    """Remove membership only; other generations and displayed readers stay intact."""
    clause, parameters = _membership_scope(scope, exclude)
    db.execute('DELETE FROM generation_entries WHERE generation=?' + clause, (generation,) + parameters)


def write_entries(db, generation, parent_id, rows):
    """Intern one bounded metadata batch with set-based SQL, avoiding row triggers."""
    db.execute('CREATE TEMP TABLE IF NOT EXISTS entry_batch(name TEXT,name_fold TEXT,'
               'directory INTEGER,size INTEGER,modified INTEGER,symlink INTEGER,identity TEXT,sort_key BLOB)')
    db.execute('DELETE FROM entry_batch')
    db.executemany('INSERT INTO entry_batch VALUES(?,?,?,?,?,?,?,?)', rows)
    db.execute('INSERT OR IGNORE INTO entry_nodes(parent_id,name,name_fold,sort_key) '
               'SELECT ?,name,name_fold,sort_key FROM entry_batch', (parent_id,))
    db.execute('INSERT OR IGNORE INTO entry_records(node_id,directory,size,modified,symlink,identity) '
               'SELECT n.id,b.directory,b.size,b.modified,b.symlink,b.identity FROM entry_batch b '
               'JOIN entry_nodes n ON n.parent_id=? AND n.name=b.name', (parent_id,))
    db.execute('INSERT OR REPLACE INTO generation_entries '
               'SELECT ?,?,n.id,r.id FROM entry_batch b '
               'JOIN entry_nodes n ON n.parent_id=? AND n.name=b.name '
               'JOIN entry_records r ON r.node_id=n.id AND r.directory=b.directory '
               'AND r.size=b.size AND r.modified=b.modified AND r.symlink=b.symlink AND r.identity=b.identity',
               (generation,parent_id,parent_id))
    db.execute('DELETE FROM entry_batch')


def delete_children(db, generation, parent):
    db.execute('DELETE FROM generation_entries WHERE generation=? '
               'AND parent_id=(SELECT id FROM folder_paths WHERE path=?)', (generation, str(parent)))


def retire_generation(db, generation):
    """Retire one scope and prune only its now-unreferenced metadata and names.

    Existing readers retain their immutable SQLite transaction. Other roots and
    partial checkpoints keep their shared records; no global metadata pass is used.
    """
    db.execute('CREATE TEMP TABLE IF NOT EXISTS retired_records(id INTEGER PRIMARY KEY)')
    db.execute('DELETE FROM retired_records')
    db.execute('INSERT OR IGNORE INTO retired_records SELECT record_id '
               'FROM generation_entries WHERE generation=?', (generation,))
    db.execute('CREATE TEMP TABLE IF NOT EXISTS retired_nodes(id INTEGER PRIMARY KEY)')
    db.execute('DELETE FROM retired_nodes')
    db.execute('INSERT OR IGNORE INTO retired_nodes SELECT node_id FROM entry_records '
               'WHERE id IN (SELECT id FROM retired_records)')
    db.execute('DELETE FROM scans WHERE id=?', (generation,))
    db.execute('DELETE FROM entry_records WHERE id IN (SELECT id FROM retired_records) '
               'AND NOT EXISTS (SELECT 1 FROM generation_entries WHERE record_id=entry_records.id)')
    db.execute('DELETE FROM entry_nodes WHERE id IN (SELECT id FROM retired_nodes) '
               'AND NOT EXISTS (SELECT 1 FROM entry_records WHERE node_id=entry_nodes.id)')
    db.execute('DELETE FROM retired_records')
    db.execute('DELETE FROM retired_nodes')


def initialize_schema(db, cancelled=lambda: False, report=lambda done, total, message: None):
    """Create or upgrade the persistent schema under the caller's writer lock."""
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == SCHEMA_VERSION:
        ensure_reader_view(db)
        # Reconciliation must look up one parent's children, not walk every
        # saved folder for every scanned folder (quadratic at disk scale).
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='folder_parent'").fetchone():
            report(0, 0, 'Optimizing saved index')
            db.execute('CREATE INDEX folder_parent ON folders(generation,parent,path)')
        db.execute('DROP INDEX IF EXISTS folder_queue_order')  # Duplicate of folder_pending.
        return
    if version not in (0, 1, 2):
        raise RuntimeError(f'Unsupported directory index version {version}; choose another index file')
    report(0, 0, 'Preparing file index' if version == 0 else 'Optimizing saved index')
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
        CREATE INDEX IF NOT EXISTS folder_parent ON folders(generation,parent,path);
        CREATE TABLE IF NOT EXISTS errors(generation INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
            path TEXT NOT NULL,error TEXT NOT NULL,PRIMARY KEY(generation,path));
        CREATE TABLE IF NOT EXISTS folder_totals(generation INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
            path TEXT NOT NULL,size INTEGER NOT NULL,files INTEGER NOT NULL,folders INTEGER NOT NULL,
            skipped INTEGER NOT NULL,extensions TEXT NOT NULL,complete INTEGER NOT NULL,scanned_at REAL NOT NULL,
            PRIMARY KEY(generation,path));
    ''')
    db.execute('DROP INDEX IF EXISTS folder_queue_order')
    upgrade_entries(db, cancelled)
