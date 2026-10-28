"""Generation validation against one captured writer context, without cache state."""
import json
from pathlib import Path
from .metadata import entry_fingerprint
from .operation import mark_totals_changed
from ...runtime.operations import check_cancelled


def validate(context, root, cancelled, report, *, folder_identity, root_only=False, check_files=True):
    db, generation, state = context.database, context.generation, context.state
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
        if state.blocks(Path(text)):
            unchanged = False
            continue
        valid = status == 'done'
        failed_path = text
        try:
            valid = valid and folder_identity(Path(text), root) == expected
            if valid and check_files:
                children = db.execute('SELECT path,identity FROM entries WHERE generation=? AND parent=?', (generation, text))
                for child, identity in children:
                    check_cancelled(cancelled)
                    state.checked_entries += 1
                    report(state.checked_entries, 0, f'Checking file metadata · {text}')
                    failed_path = child
                    if json.dumps(entry_fingerprint(child, Path(child).lstat())) != identity:
                        valid = False
                        break
        except OSError as error:
            db.execute('INSERT OR REPLACE INTO errors VALUES(?,?,?)',
                       (generation, failed_path, str(error)))
            valid = False
        if not valid:
            mark_totals_changed(state, Path(text), root)
            unchanged = False
            db.execute("UPDATE folders SET status='pending' WHERE generation=? AND path=?", (generation, text))
        count += 1
        report(state.checked_entries, 0, f'Checking indexed folder {text}')
    db.commit()
    return unchanged

