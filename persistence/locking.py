"""Advisory process locks; callers own paths, contention policy and writer scope."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import time


@contextmanager
def file_lock(path, *, timeout=0):
    """Yield whether an exclusive lock was acquired, releasing it on exit.

    The parent must exist. Contention returns False after the bounded wait;
    unrelated OS errors propagate. Never unlink the lock file: waiters must
    continue to address the same inode. Windows locks one byte beyond EOF
    without writing, avoiding a race with a concurrent first opener.
    """
    if timeout < 0:
        raise ValueError('Lock timeout cannot be negative.')
    deadline = time.monotonic() + timeout
    with Path(path).open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            def acquire():
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        acquired = False
        try:
            while True:
                try:
                    acquire()
                    acquired = True
                    break
                except OSError as error:
                    if (error.errno not in (errno.EAGAIN, errno.EACCES, errno.EDEADLK)
                            and getattr(error, 'winerror', None) not in (32, 33)):
                        raise
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(min(.02, max(0, deadline - time.monotonic())))
            yield acquired
        finally:
            if acquired:
                release()
