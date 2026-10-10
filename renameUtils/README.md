# renameUtils

Previewable bulk filename transformations and rollback-capable rename batches.

Import from `commonUtils.renameUtils`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `RenameMetadata`, `RenameRules`, `RenameEntry`, `RenamePlan`, `plan_renames`, `plan_named_renames`, `rename_path`, `RenameResult`, `apply_renames`, `undo_renames`

[Library overview](../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `RenameMetadata` | Filesystem facts supplied to a transformation; no disk access required. |
| `RenameRules` | Rules apply in pipeline order; string modes use the documented lowercase values. |
| `plan_renames` | Plan in natural filename order; no disk changes. See each entry.error before applying. |
| `plan_named_renames` | Validate explicit (source, filename) pairs with the same safety as rule-based plans. |
| `rename_path` | Rename one file, directory or link; refuse replacement unless explicitly requested. |
| `RenameResult` | Successful entries form the undo receipt; unresolved rollback errors retain paths. |
| `apply_renames` | Revalidate, stage cycles safely, and roll the entire batch back on failure/cancel. |
| `undo_renames` | Undo a successful batch if its files and original destinations are still unchanged. |
