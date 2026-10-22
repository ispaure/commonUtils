"""Generation branch seeding with explicit exclusions and transaction context."""
import os
from pathlib import Path
from ...runtime.operations import check_cancelled
from .schema import copy_entries, delete_entries
from .exclusions import is_excluded


def seed_descendants(db, generation, root, cancelled, report, *, excluded_paths):
    """Merge overlapping saved branches, preferring their most specific checkpoint."""
    sources = db.execute('SELECT root,coalesce(building,completed) FROM roots '
                         'WHERE recursive=1 AND root!=? AND (building IS NOT NULL OR completed IS NOT NULL) '
                         'ORDER BY length(root) DESC,root', (str(root),)).fetchall()
    covered = []
    for source_text, source in sources:
        check_cancelled(cancelled)
        branch = Path(source_text)
        if root not in branch.parents or is_excluded(branch, excluded_paths):
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

