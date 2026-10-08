"""Cooperative cancellation and per-item batch results without a UI dependency."""
from dataclasses import dataclass, field


class OperationCancelled(Exception):
    """Work stopped before publication; temporary work may be discarded."""


def check_cancelled(cancelled):
    if cancelled():
        raise OperationCancelled('Operation cancelled')


@dataclass
class BatchResult:
    completed: list = field(default_factory=list)
    failed: dict = field(default_factory=dict)
    remaining: list = field(default_factory=list)
    cancelled: bool = False

    def __bool__(self):
        return bool(self.completed) and not self.failed and not self.cancelled


def run_batch(items, work, *, progress=lambda done, total, message: None, cancelled=lambda: False, stop_on_error=False):
    """Finish each item before honouring cancellation, and retain per-item errors."""
    items = tuple(items)
    result = BatchResult()
    for index, item in enumerate(items):
        if cancelled():
            result.cancelled = True
            result.remaining = list(items[index:])
            break
        progress(index, len(items), f'Processing {item}')
        try:
            if work(item) is False:
                raise RuntimeError('Operation failed; see the log for details')
            result.completed.append(item)
        except Exception as error:
            result.failed[item] = str(error)
        progress(index + 1, len(items), f'{index + 1} / {len(items)} completed')
        if item in result.failed and stop_on_error:
            result.remaining = list(items[index + 1:])
            break
    return result
