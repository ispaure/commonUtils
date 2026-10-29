"""Retire tasks owned by an isolated host-test event loop."""
import asyncio
from math import isfinite
import warnings

from .settings import WAIT_TIMEOUT


def close_loop(loop, *, timeout=WAIT_TIMEOUT):
    """Cancel and drain pending tasks before closing a non-running fixture loop.

    Cancellation-resistant tasks fail cleanup rather than silently passing.
    The default executor is joined too: cancelling to_thread does not stop its
    underlying filesystem operation. Callers close app/windows first and own
    external workers that do not belong to this loop's default executor.
    This helper must never receive a live application's shared event loop.
    """
    if loop.is_closed():
        return
    if loop.is_running():
        raise RuntimeError('Cannot close a running test event loop')
    if not isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be positive')

    async def retire():
        tasks = asyncio.all_tasks(loop) - {asyncio.current_task()}
        for task in tasks:
            task.cancel()
        if tasks:
            finished, pending = await asyncio.wait(tasks, timeout=timeout)
            # Retrieve failures after cancellation, including failed finally blocks.
            errors = [task.exception() for task in finished if not task.cancelled()]
            if pending:
                raise AssertionError('Test tasks resisted cancellation: ' + repr([
                    task.get_name() for task in pending]))
            for error in errors:
                if error is not None:
                    raise error
    try:
        loop.run_until_complete(retire())
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
            # CPython otherwise warns and returns with the worker still alive.
            # That must fail a fixture before its owner removes private files.
            with warnings.catch_warnings():
                warnings.simplefilter('error', RuntimeWarning)
                try:
                    # Early Python 3.12 releases apply the executor's timeout
                    # only after awaiting its completion, so bound that await too.
                    loop.run_until_complete(asyncio.wait_for(
                        loop.shutdown_default_executor(timeout=timeout), timeout=timeout))
                except (TimeoutError, RuntimeWarning) as error:
                    raise AssertionError('Test executor did not retire before cleanup') from error
        finally:
            loop.close()
