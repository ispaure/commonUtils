# Background task presentation

Qt workers, cancellable operation progress, streamed processes and download dialogs. Runtime operations and streams remain outside the UI layer.

Import implementations from `commonUtils.ui.tasks.<module>`.
Import widgets and helpers directly from these modules. Package imports do not
eagerly load their widgets. Former flat `commonUtils.ui.<module>` forwarding
modules have been removed; update imports and mock patch targets to this package.

## Modules

- `operations`
- `operation_progress`
- `process_runner`
- `process_progress`
- `process_host`
- `download`
- `archive`: optional progress adapter for the legacy ZIP extraction entry point

[Operation progress](../operation_progress.md) and [runtime operations](../../runtime/operations/operations.md).
