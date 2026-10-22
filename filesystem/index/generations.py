"""Durable checkpoint and generation publication phases under an owned writer lease."""
from time import time, perf_counter
from .schema import retire_generation


def checkpoint(db, *, entries, saved_at, metrics, cancelled, force=False):
    """Commit bounded scan progress; return the next explicit checkpoint counters."""
    if force or cancelled() or entries >= 4096 or time() - saved_at >= .5:
        started = perf_counter()
        db.commit()
        metrics['checkpoint_seconds'] += perf_counter() - started
        metrics['checkpoints'] += 1
        return 0, time()
    return entries, saved_at


def publish_generation(db, generation, previous, root, recursive, *, complete):
    """Publish a finished replacement and retire its predecessor in one commit."""
    if complete:
        db.execute('UPDATE roots SET completed=?,building=NULL WHERE root=? AND recursive=?',
                   (generation, str(root), recursive))
        if previous:
            retire_generation(db, previous)
    db.commit()
