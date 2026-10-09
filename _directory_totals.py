"""Folder aggregates derived from the index, without another filesystem walk."""
import json
from pathlib import Path
from time import time
from .filesystem import FolderStats
from .operations import check_cancelled


def collect_folder_stats(db, generation, root, cancelled=lambda: False):
    stats = {Path(path): FolderStats(complete=status == 'done') for path, status in
             db.execute('SELECT path,status FROM folders WHERE generation=?', (generation,))}
    stats.setdefault(root, FolderStats(complete=False))
    for path, _error in db.execute('SELECT path,error FROM errors WHERE generation=?', (generation,)):
        path = Path(path)
        target = path if path in stats else path.parent
        value = stats.setdefault(target, FolderStats(complete=False))
        value.skipped += 1; value.complete = False
    # Descendants precede parents, so directory entries include already accumulated
    # child totals. Memory grows with directories, rather than every file object.
    for path, parent, directory, size, link in db.execute(
            'SELECT path,parent,directory,size,symlink FROM entries WHERE generation=? ORDER BY length(path) DESC,path',
            (generation,)):
        check_cancelled(cancelled)
        parent = Path(parent); path = Path(path)
        value = stats.setdefault(parent, FolderStats(complete=False))
        if link:
            value.skipped += 1
        elif directory:
            child = stats.setdefault(path, FolderStats(complete=False))
            value.include(child)
        else:
            value.size += size; value.files += 1
            extension = path.suffix.lower().lstrip('.')
            value.extension_counts[extension] = value.extension_counts.get(extension, 0) + 1
    return stats


def store_folder_stats(db, generation, root, cancelled=lambda: False):
    stats = collect_folder_stats(db, generation, root, cancelled)
    stamp = time()
    db.execute('SAVEPOINT aggregate_totals')
    try:
        db.execute('DELETE FROM folder_totals WHERE generation=?', (generation,))
        for path, value in stats.items():
            check_cancelled(cancelled)
            db.execute('INSERT INTO folder_totals VALUES(?,?,?,?,?,?,?,?,?)',
                       (generation, str(path), value.size, value.files, value.folders, value.skipped,
                        json.dumps(value.extension_counts), value.complete, stamp))
        db.execute('RELEASE aggregate_totals')
    except BaseException:
        db.execute('ROLLBACK TO aggregate_totals'); db.execute('RELEASE aggregate_totals')
        raise
