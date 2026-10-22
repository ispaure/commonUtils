"""Reader snapshot assembly; writer leases remain separate from read ownership."""
from pathlib import Path
from time import time
from .metadata import Snapshot
from .reader import SqlEntries, SqlDirectories
from .totals import store_folder_stats


def assemble_snapshot(database, readers, db, generation, root, recursive, *, reused=False, resumed=False, complete=True, parent=None,
              metadata_checked=True, reader=None, cancelled=lambda: False, scope=None):
    if reader is None and not db.execute('SELECT 1 FROM folder_totals WHERE generation=? LIMIT 1', (generation,)).fetchone():
        store_folder_stats(db, generation, root, cancelled)
        db.commit()
    entries = SqlEntries(database, generation, parent=parent, connection=reader, scope=scope)
    readers.add(entries)
    errors = tuple((Path(path), error) for path, error in db.execute('SELECT path,error FROM errors WHERE generation=?', (generation,)))
    scanned = db.execute('SELECT scanned_at FROM scans WHERE id=?', (generation,)).fetchone()[0]
    directories = SqlDirectories(entries)
    has_totals = db.execute("SELECT 1 FROM sqlite_master WHERE name='folder_totals'").fetchone()
    total = db.execute('SELECT complete FROM folder_totals WHERE generation=? AND path=?',
                       (generation, str(root))).fetchone() if has_totals else None
    complete = complete and (total is None or bool(total[0]))
    return Snapshot(root, recursive, entries, errors, scanned or time(), directories=directories, reused=reused,
                    validated_at=time(), resumed=resumed, complete=complete, metadata_checked=metadata_checked)

