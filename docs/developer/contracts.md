# Integration contracts

Use the module paths in the [API guide](public-apis.md). The library imports its
subsystems through ordinary Python packages. Importing the root loads no GUI,
installs no custom import hooks and initializes no subsystem.

Logistics pins commonUtils as a Git submodule. Ally Tools uses that same checkout
through its Logistics host. Blue Hole vendors the library under its own namespace;
its modules and registries are independent of a standalone commonUtils import.
Validate each consumer before updating its pinned or vendored revision.

## Data and behavior

File instances retain their original path and cached metadata. Registration changes
affect future resolutions. Feature bindings filter captured selections by accepted
types; handlers still validate current state before mutation. Read
[extension points](extension-points.md) before changing these interfaces.

Shared settings live at `ui/settings.ini`. Readers use defaults for invalid/missing
values and do not rewrite configuration. INI key changes require updating consumers
and a deliberate migration of saved values. See [configuration](../../configuration/README.md).

Cache/data locations and launcher lookup are observable behavior. SQLite schema
changes need writer locking, rollback, old-reader consistency and preservation of
resumable checkpoints. Consumers use Entry/Snapshot rather than database IDs. See
[storage](../../filesystem/storage/README.md) and [indexing](../../filesystem/index/README.md).

Text encodings, BOMs, line endings, conflict checks and unchanged-byte preservation
are format-specific contracts. Atomic replacement is not a writer lock. Preserve
explicit source editing when a formatted editor cannot round-trip a document.

## Platform and lifecycle

Windows/macOS/Linux support does not make every native adapter portable. Speech,
trash, terminals, network detection and external tools need platform validation.
The checked-in CI selects Python 3.12.2; the application owns dependency pins.
There is no formal release/version policy or tested universal dependency range.

Retain owners through cooperative shutdown and respect document close vetoes.
Browser `stop()` returns true while busy; controller `prepare_close()` returns
false while not ready. See [architecture](architecture.md#initialization-and-shutdown).

## Updating consumers

Review imports, arguments, return values, data formats and lifecycle together.
Run shared regressions and each affected consumer's tests, update their imports
and documentation, and then update the pinned or vendored source. Keep domain
workflows in the consuming application.

[Developer hub](README.md)
