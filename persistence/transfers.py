"""Transfer phase mechanics; callers retain collision, link and encoding policy."""
import errno
from ..runtime.operations import MutationIncomplete, MutationResult


def try_rename(source, destination, *, rename):
    """Return False only when a different volume requires staged copying."""
    try:
        rename(source, destination)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        return False
    return True


def verify_unchanged(expected, snapshot, *, message, error=ValueError):
    if snapshot() != expected:
        raise error(message)


def cleanup_published(remove, *, source_state):
    """Never describe failure after publication as a rolled-back transfer."""
    try:
        return remove()
    except MutationIncomplete as error:
        result = error.result
        raise MutationIncomplete('The verified destination was saved. Source cleanup is incomplete.',
            MutationResult(True, result.source_state, result.removed_paths)) from error
    except Exception as error:
        try:
            state = source_state()
        except Exception:
            state = 'unknown'
        raise MutationIncomplete('The verified destination was saved. Source cleanup is incomplete.',
                                 MutationResult(True, state)) from error
