"""Folder aggregates derived from the index, without another filesystem walk."""
import json
import os
from pathlib import Path
from time import time
from .filesystem import FolderStats
from .operations import check_cancelled



def _extension(path):
    name = path.rsplit(os.sep,1)[-1]
    dot = name.rfind('.')
    return name[dot+1:].lower() if 0<dot<len(name)-1 else ''


def collect_folder_stats(db, generation, root, cancelled=lambda: False):
    # Keep strings in the file-sized loop; construct Paths only for folder results.
    stats = {path: FolderStats(complete=status == 'done') for path, status in
             db.execute('SELECT path,status FROM folders WHERE generation=?', (generation,))}
    stats.setdefault(str(root), FolderStats(complete=False))
    for path, _error in db.execute('SELECT path,error FROM errors WHERE generation=?', (generation,)):
        target = path if path in stats else os.path.dirname(path)
        value = stats.setdefault(target, FolderStats(complete=False))
        value.skipped += 1; value.complete = False
    directories = []
    for path, parent, directory, size, link in db.execute(
            'SELECT path,parent,directory,size,symlink FROM entries WHERE generation=?', (generation,)):
        check_cancelled(cancelled)
        value = stats.setdefault(parent, FolderStats(complete=False))
        if link:
            value.skipped += 1
        elif directory:
            directories.append((path,parent))
        else:
            value.size += size; value.files += 1
            extension = _extension(path)
            value.extension_counts[extension] = value.extension_counts.get(extension, 0) + 1
    # Sort folders alone, rather than every indexed file in a SQLite temp table.
    for path,parent in sorted(directories,key=lambda item:len(item[0]),reverse=True):
        check_cancelled(cancelled)
        stats[parent].include(stats.setdefault(path,FolderStats(complete=False)))
    return {Path(path):value for path,value in stats.items()}


def collect_changed_stats(db, generation, root, paths, cancelled):
    """Recompute direct contents and roll up changed ancestors from saved children."""
    values = {}
    for path in sorted(set(paths),key=lambda item:len(str(item)),reverse=True):
        check_cancelled(cancelled)
        text = str(path)
        row = db.execute('SELECT status FROM folders WHERE generation=? AND path=?',(generation,text)).fetchone()
        if row is None:
            db.execute('DELETE FROM folder_totals WHERE generation=? AND path=?',(generation,text))
            continue
        value = FolderStats(complete=row[0]=='done')
        # A single indexed lookup reads immediate entries and their saved aggregates.
        children = db.execute('SELECT e.path,e.directory,e.size,e.symlink,t.size,t.files,t.folders,t.skipped,t.extensions,t.complete '
                              'FROM entries AS e INDEXED BY entry_parent LEFT JOIN folder_totals AS t '
                              'ON t.generation=e.generation AND t.path=e.path WHERE e.generation=? AND e.parent=?',(generation,text))
        for child,directory,size,link,child_size,files,folders,skipped,extensions,complete in children:
            check_cancelled(cancelled)
            if link:
                value.skipped += 1
            elif directory:
                cached = values.get(Path(child))
                if cached is None:
                    cached = (FolderStats(child_size,files,folders,skipped,json.loads(extensions),bool(complete))
                              if child_size is not None else FolderStats(complete=False))
                value.include(cached)
            else:
                value.size += size; value.files += 1
                extension = _extension(child)
                value.extension_counts[extension] = value.extension_counts.get(extension,0)+1
        prefix = text.rstrip(os.sep)+os.sep
        upper = prefix[:-1]+chr(ord(os.sep)+1)
        errors = db.execute('SELECT count(*) FROM (SELECT 1 FROM errors WHERE generation=? AND path=? '
                            'UNION ALL SELECT 1 FROM errors WHERE generation=? AND path>=? AND path<? '
                            'AND instr(substr(path,?),?)=0)',
                            (generation,text,generation,prefix,upper,len(prefix)+1,os.sep)).fetchone()[0]
        if errors:
            value.skipped += errors; value.complete = False
        values[path] = value
    return values


def store_folder_stats(db, generation, root, cancelled=lambda: False, *, paths=None):
    stats = (collect_folder_stats(db,generation,root,cancelled) if paths is None else
             collect_changed_stats(db,generation,root,paths,cancelled))
    stamp = time()
    db.execute('SAVEPOINT aggregate_totals')
    try:
        if paths is None:
            db.execute('DELETE FROM folder_totals WHERE generation=? AND path NOT IN '
                       '(SELECT path FROM folders WHERE generation=?)', (generation, generation))
        for path, value in stats.items():
            check_cancelled(cancelled)
            db.execute('INSERT INTO folder_totals VALUES(?,?,?,?,?,?,?,?,?) '
                       'ON CONFLICT(generation,path) DO UPDATE SET size=excluded.size,files=excluded.files,'
                       'folders=excluded.folders,skipped=excluded.skipped,extensions=excluded.extensions,'
                       'complete=excluded.complete,scanned_at=excluded.scanned_at WHERE '
                       'folder_totals.size!=excluded.size OR folder_totals.files!=excluded.files OR '
                       'folder_totals.folders!=excluded.folders OR folder_totals.skipped!=excluded.skipped OR '
                       'folder_totals.extensions!=excluded.extensions OR folder_totals.complete!=excluded.complete',
                       (generation, str(path), value.size, value.files, value.folders, value.skipped,
                        json.dumps(value.extension_counts), value.complete, stamp))
        db.execute('RELEASE aggregate_totals')
    except BaseException:
        db.execute('ROLLBACK TO aggregate_totals'); db.execute('RELEASE aggregate_totals')
        raise
