# Background task presentation

Qt workers, cancellable operation progress, streamed processes and download dialogs. Runtime operations and streams remain outside the UI layer.

Import implementations from `commonUtils.ui.tasks.<module>`.
The former `commonUtils.ui.<module>` paths remain compatibility aliases to the
same module objects, including their registries and patch targets. Package imports
do not eagerly load their widgets.

## Modules

- `operations`
- `operation_progress`
- `process_runner`
- `process_progress`
- `process_host`
- `download`

[Operation progress](../operation_progress.md) and [runtime operations](../../runtime/operations/README.md).
