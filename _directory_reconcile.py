"""Atomic, folder-scoped updates for the browser's completed persistent index.

Navigation checks immediate metadata, notifications add affected folders, and only
changed/new branches are enumerated. SQLite read transactions preserve old views;
no full generation copy or repeated descendant validation is needed. Cancellation
rolls back this update; initial/partial scans still use resumable DirectoryCache.get.
"""
import json
import os
from pathlib import Path
from time import time
from ._directory_metadata import fingerprint
from .operations import check_cancelled


def _changed(cache, db, generation, folder, source_root, cancelled, report):
    row = db.execute('SELECT identity,status FROM folders WHERE generation=? AND path=?',
                     (generation, str(folder))).fetchone()
    if row is None or row[1] != 'done':
        return True
    try:
        if cache._folder_identity(folder, source_root) != row[0]:
            return True
        for path, identity in db.execute('SELECT path,identity FROM entries WHERE generation=? AND parent=?',
                                        (generation, str(folder))):
            check_cancelled(cancelled)
            cache._checked_entries += 1
            report(cache._checked_entries, 0, 'Checking indexed files')
            if json.dumps(fingerprint(Path(path).lstat())) != identity:
                return True
    except OSError:
        return True
    return False


def reconcile_existing(cache, root, changes, cancelled, report, *, full=False):
    """Return None when a new/partial index needs its normal resumable scan."""
    if not cache.database.is_file() or not root.is_dir():
        return None
    report(0, 0, 'Waiting for index writer')
    with cache._writer(cancelled, report) as db:
        ancestors = (str(root),) + tuple(str(path) for path in root.parents)
        row = db.execute('SELECT root,completed,building FROM roots WHERE recursive=1 AND root IN ('
                         + ','.join('?' for _ in ancestors) + ') AND (completed IS NOT NULL OR building IS NOT NULL) '
                         'ORDER BY length(root) DESC LIMIT 1', ancestors).fetchone()
        if row is None or row[1] is None or row[2] is not None:
            return None
        source_root, generation = Path(row[0]), row[1]
        cache._discovered_entries = cache._checked_entries = 0
        cache._dirty_totals = set()
        cache._checkpoint_entries = 0
        cache.last_metrics = dict(metadata_seconds=0., database_write_seconds=0., aggregation_seconds=0.,
                                  validation_seconds=0., checkpoint_seconds=0., checkpoints=0)
        cache._excluded_paths = set()
        try:
            cache._excluded_paths.add(source_root / cache.database.parent.resolve().relative_to(source_root.resolve()))
        except ValueError:
            pass
        targets = {root}
        if not db.execute('SELECT 1 FROM folders WHERE generation=? AND path=?',
                          (generation, str(root))).fetchone():
            # A newly visited directory may not have existed at the last scan.
            # Check its nearest indexed ancestor to add the missing branch and
            # its parent membership before publishing recursive totals.
            for ancestor in root.parents:
                if db.execute('SELECT 1 FROM folders WHERE generation=? AND path=?',
                              (generation, str(ancestor))).fetchone():
                    targets.add(ancestor)
                    break
        for changed in changes:
            path = Path(changed).absolute()
            if path != source_root and source_root not in path.parents:
                continue
            directory = db.execute('SELECT 1 FROM folders WHERE generation=? AND path=?',
                                   (generation, str(path))).fetchone()
            if any(path == excluded or excluded in path.parents for excluded in cache._excluded_paths):
                continue
            targets.add(path if directory and path.is_dir() else path.parent)
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TEMP TABLE reconciled_folders(path TEXT PRIMARY KEY)')
            db.execute('CREATE TEMP TABLE reconcile_records(id INTEGER PRIMARY KEY)')
            checked = set()
            for folder in sorted(targets, key=lambda path: len(path.parts)):
                check_cancelled(cancelled)
                if _changed(cache, db, generation, folder, source_root, cancelled, report):
                    db.execute("INSERT OR IGNORE INTO folders VALUES(?,?,?,'pending',NULL)",
                               (generation,str(folder),str(folder.parent)))
                    cache.invalidate(folder)
                    cache._scan_folder(db, generation, source_root, True, folder, cancelled, report, checkpoint=False)
                checked.add(folder)
                db.execute('INSERT OR IGNORE INTO reconciled_folders VALUES(?)', (str(folder),))
            if full:
                # Explicit Refresh validates descendants in the same generation,
                # retaining ancestor totals and avoiding a duplicate subtree root.
                # Read fixed-size batches: do not materialize a disk-sized queue.
                prefix = str(root).rstrip(os.sep) + os.sep
                upper = prefix[:-1] + chr(ord(os.sep) + 1)
                cursor = ''
                while True:
                    rows = db.execute('SELECT path FROM folders WHERE generation=? '
                                      'AND (path=? OR (path>=? AND path<?)) '
                                      'AND path>? AND path NOT IN (SELECT path FROM reconciled_folders) '
                                      'ORDER BY path LIMIT 256', (generation,str(root),prefix,upper,cursor)).fetchall()
                    if not rows:
                        break
                    cursor = rows[-1][0]
                    for (text,) in rows:
                        check_cancelled(cancelled)
                        if not db.execute('SELECT 1 FROM folders WHERE generation=? AND path=?',
                                          (generation,text)).fetchone():
                            continue  # A checked parent removed this cached branch.
                        folder = Path(text)
                        if _changed(cache, db, generation, folder, source_root, cancelled, report):
                            cache.invalidate(folder)
                            cache._scan_folder(db, generation, source_root, True, folder, cancelled, report, checkpoint=False)
                        checked.add(folder)
                        db.execute('INSERT OR IGNORE INTO reconciled_folders VALUES(?)', (text,))
            # Scanning changed parents adds only new/changed child folders to the
            # pending queue. Existing unchanged descendant folders remain done.
            while True:
                rows = db.execute("SELECT path FROM folders WHERE generation=? AND status='pending' "
                                  'AND path NOT IN (SELECT path FROM reconciled_folders) '
                                  'ORDER BY path LIMIT 256', (generation,)).fetchall()
                pending = [Path(path) for (path,) in rows]
                if not pending:
                    break
                for folder in pending:
                    check_cancelled(cancelled)
                    cache._scan_folder(db, generation, source_root, True, folder, cancelled, report, checkpoint=False)
                    checked.add(folder)
                    db.execute('INSERT OR IGNORE INTO reconciled_folders VALUES(?)', (str(folder),))
            if cache._dirty_totals:
                report(0, 0, 'Saving folder sizes')
                cache._publish_totals(db, generation, source_root, cancelled)
            # Prune only records touched by this update, preserving references
            # from overlapping roots/generations and old SQLite read snapshots.
            db.execute('CREATE TEMP TABLE reconcile_nodes(id INTEGER PRIMARY KEY)')
            db.execute('INSERT OR IGNORE INTO reconcile_nodes SELECT node_id FROM entry_records '
                       'WHERE id IN (SELECT id FROM reconcile_records)')
            db.execute('DELETE FROM entry_records WHERE id IN (SELECT id FROM reconcile_records) '
                       'AND NOT EXISTS (SELECT 1 FROM generation_entries WHERE record_id=entry_records.id)')
            db.execute('DELETE FROM entry_nodes WHERE id IN (SELECT id FROM reconcile_nodes) '
                       'AND NOT EXISTS (SELECT 1 FROM entry_records WHERE node_id=entry_nodes.id)')
            stamp = time()
            db.executemany('INSERT OR REPLACE INTO folder_checks VALUES(?,?,?)',
                           [(generation, str(folder), stamp) for folder in checked])
            check_cancelled(cancelled)
            db.commit()
        except BaseException:
            db.set_progress_handler(None, 0)
            db.rollback()
            raise
        return cache._snapshot(db, generation, root, True, reused=True, metadata_checked=full,
                               scope=root if root != source_root else None, cancelled=cancelled)
