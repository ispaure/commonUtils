"""Bounded asynchronous polling without importing a GUI toolkit."""
import asyncio
from math import isfinite
from time import monotonic

from .settings import (POLL_INTERVAL, WAIT_TIMEOUT, KEYBOARD_INTERVAL,
                       KEYBOARD_ATTEMPTS, KEYBOARD_STABLE_SAMPLES)


def _positive(value, name):
    if not isfinite(value) or value <= 0:
        raise ValueError(name + ' must be finite and positive')


async def wait_until(predicate, *, timeout=WAIT_TIMEOUT, interval=POLL_INTERVAL,
                     message='Condition did not become ready'):
    """Return the first truthy observation or fail at a monotonic deadline.

    The predicate is synchronous and must not block. Its exceptions and task
    cancellation propagate. A callable message is evaluated only on timeout, so it
    can describe the final observed state without doing work on every poll.
    """
    _positive(timeout, 'timeout')
    _positive(interval, 'interval')
    deadline = monotonic() + timeout
    first = True
    while True:
        if not first and monotonic() > deadline:
            raise AssertionError(message() if callable(message) else message)
        first = False
        value = predicate()
        if value and monotonic() <= deadline:
            return value
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise AssertionError(message() if callable(message) else message)
        await asyncio.sleep(min(interval, remaining))


async def wait_for_assertion(check, *, timeout=WAIT_TIMEOUT, interval=POLL_INTERVAL):
    """Retry transient assertion failures; retain the final failure details.

    Other exceptions are errors, not evidence of an unsettled UI. Passing once is
    enough; checks requiring consecutive observations should use a dedicated policy.
    """
    _positive(timeout, 'timeout')
    _positive(interval, 'interval')
    deadline = monotonic() + timeout
    last_error = None
    while True:
        if last_error is not None and monotonic() > deadline:
            raise last_error
        try:
            result = check()
            if monotonic() <= deadline:
                return result
            raise last_error or AssertionError('Assertion completed after its deadline')
        except AssertionError as error:
            last_error = error
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise
        await asyncio.sleep(min(interval, remaining))


async def settled_keyboard(request, visible, *, ready=lambda: True,
                           attempts=KEYBOARD_ATTEMPTS, interval=KEYBOARD_INTERVAL,
                           stable_samples=KEYBOARD_STABLE_SAMPLES):
    """Request focus until the served input and visible IME agree repeatedly.

    Native callbacks are supplied by the caller. A transient hide restarts the
    stability count and allows another request. Return False after the fixed budget;
    do not silently accept a keyboard belonging to a different input.
    """
    for name, value in (('attempts', attempts), ('stable_samples', stable_samples)):
        if type(value) is not int or value <= 0:
            raise ValueError(name + ' must be a positive integer')
    _positive(interval, 'interval')
    consecutive = 0
    for _ in range(attempts):
        if not consecutive:
            request()
        await asyncio.sleep(interval)
        if ready() and visible():
            consecutive += 1
            if consecutive == stable_samples:
                return True
        else:
            consecutive = 0
    return False
