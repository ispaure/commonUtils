# Diagnostics and error presentation

Import `log`, `Severity`, `DebugException` and `noninteractive_logging` from
`commonUtils.runtime.diagnostics`. This is the established diagnostic API used by
legacy file/platform helpers, not an adapter to Python's standard logging module.

`log(severity, title, message, popup=False)` prints a diagnostic. CRITICAL raises
DebugException after logging; ERROR alone does not imply an exception. A popup can
be requested explicitly, and critical diagnostics normally use the UI facade too.
Callers must distinguish that behavior from newer APIs that propagate OSError or
return an explicit result object.

Use the context manager **inside the worker or headless operation** to suppress
dialogs while preserving logs and exceptions:

```python
from commonUtils.runtime.diagnostics import log, Severity, noninteractive_logging

with noninteractive_logging():
    log(Severity.INFO, 'Example', 'Running without interactive error dialogs')
```

The manager restores the previous policy on exit, including exceptions. It uses
context-local state; enter it in the execution context that runs the operation.
Shared workers capture failures there and let the GUI owner present them after
worker completion. Do not touch widgets or display modal dialogs from workers.

Module configuration such as `verbose_debug`, `write_to_log` and `project_prefix`
serves consumers. When changing it, set the value on the module rather than
copying a setting with `from ... import ...`. There is no universal library-wide error policy: consult each
operation's contract and inspect both worker errors and per-item results.

[Runtime overview](../README.md) · [Lifecycle guidance](../../docs/developer/architecture.md)
