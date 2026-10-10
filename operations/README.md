# operations

Cooperative cancellation and per-item batch results without a UI dependency.

Import from `commonUtils.operations`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `OperationCancelled`, `check_cancelled`, `BatchResult`, `run_batch`

[Library overview](../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `OperationCancelled` | Work stopped before publication; temporary work may be discarded. |
| `run_batch` | Finish each item before honouring cancellation, and retain per-item errors. |
