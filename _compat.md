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
