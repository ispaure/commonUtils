# operations

Cooperative cancellation and per-item batch results without a UI dependency.

Import from `commonUtils.runtime.operations`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `OperationCancelled`, `check_cancelled`, `BatchResult`, `run_batch`

[Library overview](../../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `OperationCancelled` | Work stopped before publication; temporary work may be discarded. |
| `run_batch` | Finish each item before honouring cancellation, and retain per-item errors. |

## Finish the current item before cancelling a batch

Use `operations.run_batch` when each item has a transaction that must finish before
the next cancellation boundary. For example, each comic rebuild verifies and
publishes its own archive before the batch stops.

```python
from commonUtils.runtime.operations import run_batch

# These callables/inputs belong to your application.
def process_documents(documents, rebuild_one, report, cancelled):
    return run_batch(documents, rebuild_one,
                     progress=report, cancelled=cancelled)
```

The result has `completed` (list), `failed` (item → message), `remaining` (list) and
`cancelled` (bool). A work callback returning exactly `False` counts as failure;
other return values count as success unless an exception is raised. Failures
normally do not prevent later items from running. Supply `stop_on_error=True` to
stop on the first failure and retain the remainder.

Successful items need not be hashable. Items must be hashable if they can fail,
because failures are dictionary keys; stop-on-error follows the current attempt's
outcome rather than looking a successful item up in that dictionary.
Progress counts processed items, including failures, so inspect the result instead
of assuming a full progress bar means success. Cancellation after the final item
has completed does not undo its success. Do not pass the batch cancellation callback
into `rebuild_one` if the intended policy is to finish the current item. Finer-grained
cancellation belongs to a different transaction policy.

To use this with `OperationProgress`, pass a callback such as
`lambda report, cancelled: process_documents(paths, rebuild_one, report, cancelled)`.
Inspect both the worker error string and the returned batch's failure dictionary.
