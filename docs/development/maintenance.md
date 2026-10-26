# Maintenance and validation

Start with [architecture](architecture.md) and [integration contracts](contracts.md).
Keep domain workflows and software manifests in consumers. Reusable behavior and
its tests belong here. Avoid restructuring Python packages to fit documentation.

## Documentation ownership

| Change | Update |
| --- | --- |
| Public import, return value or failure contract | [API map](public-apis.md), owning `docs/development/reference/` guide, integration contracts when needed |
| Registration, controller or provider protocol | [Extension points](extension-points.md), feature examples and focused tests |
| Worker, index or persistence lifecycle | [Architecture](architecture.md) and owning technical guide |
| Shared interactive behavior or settings | `docs/user/` and relevant embedding guide |
| Consumer-specific workflow | Consumer documentation; link shared guides instead of copying them |
| Setup or dependency requirements | [Getting started](getting-started.md) and relevant module reference |

Keep README a developer entry point. Preserve useful package references and stable
links. A new guide needs substantive content and a link from its owner/navigation.
Do not invent API stability or a supported dependency range from naming alone.

## Run tests

From the checkout's parent with the project's interpreter:

```sh
QT_QPA_PLATFORM=offscreen python -m unittest commonUtils.tests.filesystem.test_file_registry commonUtils.tests.tooling.test_package_layout
```

The [test guide](reference/tests/tests.md) gives suite commands and PowerShell setup.
For many Qt modules, run separate processes to isolate QApplication and native
ownership. Use temporary cache databases, fixtures and output directories; never
point test browsers at a live user index. Keep worker owners until they stop.

The checked-in [.github workflow](https://github.com/ispaure/commonUtils/blob/main/.github/workflows/shared-checks.yml) uses the
Logistics locked environment and its isolated-module regression runner on Linux,
macOS and Windows. Read the actual workflow before reproducing CI: a local test
pass is not evidence that hosted CI or another consumer passed.

For documentation-only edits, verify relative files and heading anchors, compile
Python snippets, execute self-contained examples with temporary fixtures, and run
focused tests backing changed contract descriptions. Snippets showing embedding
fragments need host objects; validate their imports/signatures and the runnable
host example instead of pretending they run independently.

## Areas needing focused coverage

- Registry priority, owner toggles, subclass overrides, old/new module identity.
- File snapshot returns, destination preservation, traversal/link behavior.
- Index migration, partial resume, cancellation, old readers and event-driven updates.
- Save conflicts, encoding, unsupported source preservation and close vetoes.
- Selection filtering, controller lifetime, stale actions and workspace retirement.

Native dialogs, speech voices, terminal windows, trash and external applications
also need manual platform checks. Blue Hole adapter regressions require its checkout
and environment; absence should be reported, not treated as a pass.

[Developer hub](development.md)
