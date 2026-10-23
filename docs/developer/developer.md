# Developer documentation

commonUtils owns reusable mechanisms; the consuming application chooses workflows,
domain policy, dependency installation and user-facing destinations.

1. [Getting started](getting-started.md): checkout layout, dependencies and first use.
2. [Architecture](architecture.md): subsystem boundaries, state and lifecycle.
3. [Public APIs](public-apis.md): select an interface and understand its contract.
4. [Extension points](extension-points.md): add file types and browser capabilities.
5. [Integration contracts](contracts.md): imports, persistent formats and consumer upgrades.
6. [Maintenance](maintenance.md): validation and documentation responsibilities.

Detailed API examples live in the [API reference](../reference/reference.md), grouped by source owner.
For interactive workflows, use the [component user guides](../user/user.md).
The [audit record](audit.md) explains the restructuring and remaining uncertainties.
The [indexing and Markdown readability record](readability.md) defines the active
maintenance pass, completion criteria and validation scope.

[Process, diagnostics and presentation owners](lifecycle-owners.md) describes lifecycle boundaries.

[Library overview](../overview.md)

## Platform support

Windows, macOS and Linux retain their existing APIs. iOS and Android have an
incremental infrastructure foundation, not device-verified application support.
See the [compatibility audit and deployment blockers](mobile-foundation.md).

[Mobile test guide](mobile-testing.md): manually run the embedded Android/iOS
smoke harness, inspect evidence and distinguish host checks from mobile results.

## Resource integration

Use the [resource runtime map](../reference/runtime/resources/resources.md) for storage
contracts and virtual paths, and [Qt resource windows](../reference/ui/resources/resources.md)
for picker/editor operation ownership. Shared native browsing and speech lifetimes
are covered in the [native browser](../reference/ui/native_browser/native_browser.md) and
[reader controls](../reference/ui/readers/readers.md) guides.
