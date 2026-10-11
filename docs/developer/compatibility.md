# Compatibility and consumer upgrades

There is no documented semantic-versioning policy or blanket stability guarantee.
Treat established exports, documented examples, tested aliases and consumer use
as compatibility evidence. An unprefixed helper name alone is insufficient.

## Imports and identity

New code uses canonical responsibility-based paths such as
`commonUtils.filesystem.files`, `commonUtils.filesystem.directories`,
`commonUtils.formats.registry` and `commonUtils.ui.features`.

[_compat.py](../../_compat.py) is the single historical import map. Examples include
`fileUtils`, `dirUtils` and `directory_index`. Aliases must return the canonical
module object, including nested imports, so classes, registries, caches, reloads
and patch targets remain shared. Do not create duplicate compatibility packages.

The importing package's namespace matters: Blue Hole's vendored namespace and a
standalone commonUtils import must remain independent. Logistics pins commonUtils
as a Git submodule; Blue Hole uses a vendored subtree. Validate each available
consumer before updating it; do not infer compatibility from one application's
successful startup. The former layout has a `commonUtils-Pre-Refactor` checkpoint.

## Behavior and persisted state

Preserve file method return semantics, extension precedence, accepted selection
filtering, lazy imports and registration timing. Keep declared UI constructors,
methods, signals and established widget fields compatible. Some consumers also
import concrete browser/model modules; consult call sites before moving them.

Shared settings remain at `ui/settings.ini`. INI key renames require consumer
fallbacks/migration, not just a visual editor update. `get_setting` falls back on
invalid/missing values and must not rewrite user configuration during reads.
Cache/data paths and launcher lookup are observable contracts; see
[storage](../../filesystem/storage/README.md).

SQLite schema changes require migration under the writer lock, preservation of
completed snapshots and resumable partial checkpoints, and rollback on failure or
cancellation. Old read snapshots must remain valid. Schema 1/2 to 3 upgrades retain
a recovery backup; details belong in the [index guide](../../filesystem/index/README.md).
Consumers use Entry/Snapshot, not raw database table IDs.

Text encodings, BOMs, line endings, conflict checks and unchanged-byte preservation
are format-specific contracts. Atomic replacement does not authorize silent loss
of unsupported Markdown or concurrent edits. Retain the source-mode escape hatch.

## Platform and lifecycle constraints

Windows/macOS/Linux support does not make every native adapter portable. Speech,
trash, terminal launching, network detection and external application lookup need
platform validation. The current CI selects Python 3.12.2; no dependency version
range is guaranteed by a standalone packaging manifest.

Preserve cooperative worker retirement and close vetoes. In particular browser
`stop()` and controller `prepare_close()` have opposite busy/ready boolean meanings.
Hidden compatibility controls are not necessarily visible user features.

## Upgrade checklist

1. Review changed imports, signatures, configuration/cache formats and native tools.
2. Run focused shared tests and the affected consumer's integration tests.
3. Exercise close/cancel/save failures and relevant native UI behavior.
4. Update developer contracts and component user guides with the change.
5. Update pins/vendored copies only within a separately authorized consumer change.

[Developer hub](README.md)
