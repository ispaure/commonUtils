# commonUtils

commonUtils is a reusable Python library for file automation and desktop tools.
It provides filesystem objects and format registration, persistent directory
indexing, archive and process operations, configuration and atomic persistence,
shared Qt browsers, readers and editors, and optional native mobile components.
Portable resource and speech mechanisms remain independent of toolkit presentation.
Applications supply their own workflows, domain file types, dependency policy and settings.

Logistics and Blue Hole are existing consumers. Application features built on
these components remain owned by their consuming projects.

## Get started

Place the checkout in a directory named `commonUtils`, with its **parent** on
Python's import path. There is no pip-installable distribution or standalone
dependency lockfile in this repository. Python 3.10 syntax is used; the checked-in
CI configuration tests Python 3.12.2 on Windows, macOS and Linux. Compatibility
with every newer Python/dependency version is not established.

```text
my_project/
├── example.py
└── commonUtils/
```

Install only the dependencies for the components you use. The following example
needs Python's standard library; widgets require PySide6. See
[setup and dependencies](getting-started.md) for environment details.

```python
import sys
from commonUtils.integrations.wrappers.cmdShellWrapper import run_command

result = run_command([sys.executable, '--version'], timeout=10)
if result.success:
    print('\n'.join(result.stdout))
else:
    print(result.returncode, result.stderr, result.timed_out, result.cancelled)
```

## Developer documentation

Start at the [developer hub](development.md).

| Task | Guide |
| --- | --- |
| Integrate the library | [Getting started](getting-started.md) |
| Understand ownership and lifecycle | [Architecture](architecture.md) |
| Choose APIs and handle failures | [Public APIs](public-apis.md) |
| Register formats, actions and information providers | [Extension points](extension-points.md) |
| Upgrade an existing consumer | [Integration contracts](contracts.md) |
| Contribute and validate changes | [Maintenance](maintenance.md) |

## Package overview

| Area | Capabilities and detailed reference |
| --- | --- |
| [filesystem](reference/filesystem/filesystem.md) | Files, directories, links, traversal, transfers, removal, rename, storage and indexes |
| [formats](reference/formats/formats.md) | File registry; text, CSV, JSON, XML, INI, Markdown and archive types |
| [archives](reference/archives/archives.md) | Create, inspect, extract, edit and verify archives |
| [search](reference/search/search.md) | Filename/provider queries, document matching and text-file content search |
| [runtime](reference/runtime/runtime.md) | Platform detection, diagnostics, cancellation, batches, streams and downloads |
| [integrations](reference/integrations/integrations.md) | Applications, web links, Steam and external command adapters |
| [configuration](reference/configuration/configuration.md) | Settings reads, optional typed INI schema and editor integration |
| [persistence](reference/persistence/persistence.md) | Atomic publication, text snapshots, recovery and merge models |
| [ui](reference/ui/ui.md) | PySide widgets, browser extensions, workspaces, readers and editors |

[Launchers](reference/launchers/launchers.md) support consumer project startup; they are not a
library installer. Optional native tools and platform restrictions belong to the
operation that uses them.

## Shared component user guides

These guides describe reusable behavior; host applications may add commands or
choose which components to expose.

- [File Browser: navigation, search, size maps and tabs](../user/file_browser/file_browser.md)
- [Markdown: reading, editing, properties and diagrams](../user/markdown/markdown.md)
- [Code editing and diff/merge review](../user/code_editor/code_editor.md)
- [Archive contents and previews](../user/archive_view/archive_view.md)
- [Shared text and INI editors](../user/components/components.md)
- [Native list/tile browsing](../user/native_browser/native_browser.md)
- [Native component workflows](../user/native/native.md)

## Contributing

Use the current import paths and [integration contracts](contracts.md).
There is no documented semantic
versioning or universal API stability promise. Test affected consumers before
updating pinned or vendored revisions. See [contributor guidance](../../AGENTS.md).

## License

[MIT](../../LICENSE.md). Copyright © 2020–2026 Marc-André Voyer.
