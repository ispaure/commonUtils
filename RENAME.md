# Rename engine

`commonUtils.renameUtils` provides Qt-independent filename transformations,
rename planning, no-overwrite batch execution, rollback and in-memory undo receipts.
Applications own selection, previews, presets and windows. Logistics owns its
bulk rename UI in `ui_new.bulk_rename`.

```python
from pathlib import Path
from commonUtils.renameUtils import RenameRules, plan_renames, apply_renames, undo_renames
from commonUtils.traversal import scan_directory

paths = scan_directory('/path/to/photos', mask='*.jpg')
plan = plan_renames(paths, RenameRules(prefix='Photo_', number_mode='suffix'))
if plan.valid and plan.changes:
    receipt = apply_renames(plan)
    if receipt.success:
        undo_renames(receipt)
```

Planning collects source metadata once. `RenameRules.transform(path, index=0,
metadata=None, now=None)` performs no filesystem reads. Its default metadata
represents a file; supply `RenameMetadata(is_directory=True)` for a directory.
Modified/created date rules require their respective datetime metadata; Today
uses `now` or the current time. `RenameMetadata.from_stat(info)` adapts an existing
stat result. Transform returns a basename; planning validates it before use.

Plans preserve each item's parent directory, reject collisions and parent/child
selections, and default to conservative case/Unicode collision checks.
`case_sensitive=True` permits distinct-case names. Apply rechecks source stamps
and destinations, stages all sources to support cycles and case-only renames,
and never overwrites a racing destination. Cancellation between renames rolls
back the batch. Invalid/stale plans raise before modification; handled execution
failures return `RenameResult` with error/cancellation and any recovery paths.
Do not delete `.bulk-rename-*` entries reported for manual recovery. Transactions
provide rollback for handled errors, not recovery from process or machine crashes.
Undo revalidates changed files and original destinations using the receipt.

Apply/undo accept `cancelled()` and `report(done, total, message)` callbacks.
Cancellation uses the shared `OperationCancelled` exception, also exposed as
`RenameCancelled`. Callbacks must not touch GUI objects from background workers.

`commonUtils.traversal.scan_directory()` supports masks/regex, hidden entries,
files/folders, recursion and depth limits without following directory links.
Zero depth means unlimited; one includes immediate subfolder contents. It returns
paths in natural order and raises `OperationCancelled` on cancellation. Unlike
`Directory.list_files()`, it does not resolve file-type classes or follow links.

`rename_path(source, target, overwrite=False)` is the single-item primitive,
which propagates errors and requires an existing parent. `fileUtils.rename_file`
retains its boolean/logging API and parent creation, but consistently refuses
existing destinations unless `force=True`. Forced replacement uses `os.replace`
without first deleting the destination. Same-path renames are successful no-ops
for existing sources; use batch planning for portable case-only renames.
