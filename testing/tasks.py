"""Keep repeated native lifecycle callbacks from starting duplicate checks."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------


def start_once(owner, coroutine_factory, *, loop, attribute='_test_task'):
    """Retain the first task, including after completion or failure.

    The factory is lazy so repeated callbacks do not create unawaited coroutines.
    Callers choose the owner/attribute; no process-wide app registry is installed.
    """
    task = getattr(owner, attribute, None)
    if task is None:
        task = loop.create_task(coroutine_factory())
        setattr(owner, attribute, task)
    return task
