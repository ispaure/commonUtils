# Developer documentation

commonUtils owns reusable mechanisms; the consuming application chooses workflows,
domain policy, dependency installation and user-facing destinations.

1. [Getting started](getting-started.md): checkout layout, dependencies and first use.
2. [Architecture](architecture.md): subsystem boundaries, state and lifecycle.
3. [Public APIs](public-apis.md): select an interface and understand its contract.
4. [Extension points](extension-points.md): add file types and browser capabilities.
5. [Integration contracts](contracts.md): imports, persistent formats and consumer upgrades.
6. [Maintenance](maintenance.md): validation and documentation responsibilities.

Detailed API examples remain beside their owners and are linked from these guides.
For interactive workflows, use the [component user guides](../../README.md#shared-component-user-guides).
The [audit record](audit.md) explains the restructuring and remaining uncertainties.
The [indexing and Markdown readability record](readability.md) defines the active
maintenance pass, completion criteria and validation scope.

[Process, diagnostics and presentation owners](lifecycle-owners.md) describes lifecycle boundaries.

[Library overview](../../README.md)

## Platform support

Windows, macOS and Linux retain their existing APIs. iOS and Android have an
incremental infrastructure foundation, not device-verified application support.
See the [compatibility audit and deployment blockers](mobile-foundation.md).

[Mobile test guide](mobile-testing.md): manually run the embedded Android/iOS
smoke harness, inspect evidence and distinguish host checks from mobile results.

## Resource integration

Use the [resource runtime map](../../runtime/resources/README.md) for storage
contracts and virtual paths, and [Qt resource windows](../../ui/resources/README.md)
for picker/editor operation ownership. Shared native browsing and speech lifetimes
are covered in the [native browser](../../ui/native_browser/README.md) and
[reader controls](../../ui/readers/README.md) guides.
