# Package layout

CommonUtils is shared by exactly two maintained consumers: Logistics (a pinned
Git submodule) and Blue Hole (a vendored Git subtree). Keep both copies aligned
when changing the shared API.

The root contains eight implementation areas, `launchers`, `tests`, package
initialization, the centralized compatibility adapter, README and license. Place
new code in the area that owns its responsibility. Do not create a top-level
package for each helper or compatibility name.

| Area | Owns |
| --- | --- |
| filesystem | Path objects, files, directories, links, rename, traversal, transfers, removal, storage and the directory index |
| formats | File type classes, registry, Markdown and spreadsheet helpers |
| archives | Archive operations, ZIP access and legacy archive convenience functions |
| runtime | OS detection, diagnostics, logging, cancellation, progress, streams and downloads |
| integrations | Desktop applications, web links, Steam and external command adapters |
| configuration | Settings, INI schemas and the legacy config API |
| persistence | Atomic writes, recovery, sessions and text merging |
| ui | Native/PySide interfaces, browser features, readers and editors |

Modules with multiple implementation files retain their own package. Package guides live in each area’s `README.md`. Module-specific guides
sit beside the implementation with the same stem, such as `zip_access.md`
and `xmlType.md`. Keep examples with their owning API; do not recreate a
central `docs/` folder.

## Compatibility and reconciliation

`_compat.py` is the single historical import map. It loads only requested modules
and returns the canonical module object, including nested submodules. Old imports,
feature class references and patch targets therefore share classes, caches and
state with the new paths. It uses the importing package's own name, so Blue Hole's
vendored namespace remains independent of Logistics' namespace. New application
and shared-library imports use canonical paths.

The file helper's project-directory calculation accounts for its extra directory
level. The settings INI remains at `ui/settings.ini`. User caches, application
data and launcher locations remain stable.

The former layout was checkpointed as `commonUtils-Pre-Refactor`. Previous passes
wrapped helper modules in same-named top-level packages; this pass groups those
packages by responsibility and removes the separate compatibility directories.

## Validation

Run shared and application regressions with the pinned Logistics interpreter;
run Blue Hole's adapter regressions without Blender startup. The layout tests
cover alias identity, nested packages, reload, lazy dependencies and vendored
namespace isolation. CI exercises all supported desktop platforms and source
release packaging.

## Filesystem and operation contracts

- Directory traversal follows directory links while detecting recursive loops.
  Deleting a Directory that represents a symbolic link or junction removes the
  link itself, retaining its target.
- `Directory.delete_contents()` refuses a linked root unless
  `follow_root_link=True` explicitly permits target-content deletion.
- `linkUtils.update_symbolic_link()` refuses to replace a real destination unless
  `allow_destination_deletion=True` is supplied.
- Cancellation is cooperative. Stream helpers check between chunks; a blocking
  read must return before cancellation can be observed. The caller owns staging
  and transaction boundaries.
- `OperationProgress.completed(result, error)` arrives after worker shutdown.
  Keep the owner alive until then and route close/Escape to cancellation during work.
- `run_batch` finishes each item before observing cancellation. Its result records
  completed items, per-item failures and the unprocessed remainder. An error-free
  Qt callback can still return a batch containing individual failures.
- Downloads verify both release and installed hashes before promotion. Applications
  supply URLs, versions, platform choice and destination; commonUtils does not
  automatically choose software or install drivers.
- ZIP creation preserves sources and existing destinations, verifies decrypted
  content and checks cancellation before publication. Extraction is staged per
  file, rather than a transaction across the whole archive. See the archive guide.
- `cmdShellWrapper.exec_cmd(time_out=...)` uses an **idle-output timeout**, not a
  maximum runtime; ongoing output can keep the command alive.

These contracts are operation-specific. A shared stream copy alone does not make
a file replacement atomic, and using a progress widget does not make arbitrary
callbacks cancellable.

## Package layout and compatibility

Directory indexing lives in `filesystem/index/`: `metadata`, `store`, `schema`,
`scan`, `reader`, `search`, `order`, `totals`, `exclusions` and `reconcile`.
Import its public API from `commonUtils.filesystem.index`; its cache remains process-wide.
Atomic publication lives in `persistence/`, with text documents in
`persistence.text` and session recovery in `persistence.session`.

Historical public paths remain lazy aliases in `_compat.py`. Canonical and legacy
imports share module state, classes, cache instances and instrumentation, including
nested submodules. The configuration helper now lives in `configuration/legacy.py`.

Logistics uses the canonical imports and pins this repository as a Git submodule.
Blue Hole vendors the same implementation as a subtree and uses canonical imports
under its own package namespace. See [area boundaries](#package-layout) for the
area boundaries and reconciliation checks.
