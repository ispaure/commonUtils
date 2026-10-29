"""Keep repeated native lifecycle callbacks from starting duplicate checks."""


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
