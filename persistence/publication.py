"""Serialized verified save transactions and atomic no-replace publication."""
import ctypes
import errno
import os
import threading
from ..runtime.operations import check_cancelled, MutationResult, MutationIncomplete


mutation_lock = threading.RLock()


def serialize_mutation(function):
    from functools import wraps
    @wraps(function)
    def invoke(*args, **kwargs):
        with mutation_lock:
            return function(*args, **kwargs)
    return invoke


def save_transaction(*, stage, verify, validate, publish, cleanup, cancelled=lambda: False):
    """Run one verified publication under the process mutation lock.

    stage owns exclusive allocation and partial-write cleanup. cleanup removes only
    its owned stage and must be safe after publication. verify may return a value.
    validate runs before staging and again immediately before publication.
    Cancellation after publication is deliberately not reported as a failed save.
    """
    with mutation_lock:
        check_cancelled(cancelled)
        validate()
        published = False
        try:
            stage()
            check_cancelled(cancelled)
            result = verify()
            validate()
            check_cancelled(cancelled)
            publish()
            published = True
            return result
        finally:
            try:
                cleanup()
            except Exception as error:
                message = ('The verified destination was saved, but temporary cleanup failed.' if published else
                           'The destination was not published, but temporary cleanup failed.')
                raise MutationIncomplete(message, MutationResult(destination_published=published)) from error


def rename_exclusive(source, destination):
    """Atomic no-replace publication; fail closed on unsupported platforms."""
    source, destination = os.fsencode(source), os.fsencode(destination)
    from ..runtime.platform import get_os, OS
    current = get_os()
    if current is OS.WIN:
        os.rename(source, destination)  # Windows rename rejects existing targets.
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if current in {OS.MAC, OS.IOS}:
        function = getattr(libc, 'renamex_np', None)
        argument_types = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        arguments = (source, destination, 4)  # RENAME_EXCL
    elif current in {OS.LINUX, OS.ANDROID}:
        function = getattr(libc, 'renameat2', None)
        argument_types = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        arguments = (-100, source, -100, destination, 1)  # AT_FDCWD, RENAME_NOREPLACE
    else:
        function = None
    if function is None:
        raise OSError(errno.ENOTSUP, 'This platform lacks exclusive rename support', os.fsdecode(destination))
    function.argtypes = argument_types
    function.restype = ctypes.c_int
    if function(*arguments):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), os.fsdecode(destination))
