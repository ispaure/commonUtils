# commonUtils

commonUtils is a reusable Python library for file automation and desktop tools.
It provides filesystem objects and format registration, persistent directory
indexing, archive and process operations, configuration and atomic persistence,
and shared Qt browsers, readers and editors. Applications supply their own
workflows, domain file types, dependency policy and settings.

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
[setup and dependencies](docs/developer/getting-started.md) for environment details.

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

Start at the [developer hub](docs/developer/README.md).

| Task | Guide |
| --- | --- |
| Integrate the library | [Getting started](docs/developer/getting-started.md) |
| Understand ownership and lifecycle | [Architecture](docs/developer/architecture.md) |
| Choose APIs and handle failures | [Public APIs](docs/developer/public-apis.md) |
| Register formats, actions and information providers | [Extension points](docs/developer/extension-points.md) |
| Upgrade an existing consumer | [Integration contracts](docs/developer/contracts.md) |
| Contribute and validate changes | [Maintenance](docs/developer/maintenance.md) |

## Package overview

| Area | Capabilities and detailed reference |
| --- | --- |
| [filesystem](filesystem/README.md) | Files, directories, links, traversal, transfers, removal, rename, storage and indexes |
| [formats](formats/README.md) | File registry; text, CSV, JSON, XML, INI, Markdown and archive types |
| [archives](archives/README.md) | Create, inspect, extract, edit and verify archives |
| [runtime](runtime/README.md) | Platform detection, diagnostics, cancellation, batches, streams and downloads |
| [integrations](integrations/README.md) | Applications, web links, Steam and external command adapters |
| [configuration](configuration/README.md) | Settings reads, optional typed INI schema and editor integration |
| [persistence](persistence/README.md) | Atomic publication, text snapshots, recovery and merge models |
| [ui](ui/README.md) | PySide widgets, browser extensions, workspaces, readers and editors |

[Launchers](launchers/README.md) support consumer project startup; they are not a
library installer. Optional native tools and platform restrictions belong to the
operation that uses them.

## Shared component user guides

These guides describe reusable behavior; host applications may add commands or
choose which components to expose.

- [File Browser: navigation, search, size maps and tabs](ui/file_browser/user_docs/README.md)
- [Markdown: reading, editing, properties and diagrams](ui/markdown/user_docs/README.md)
- [Code editing and diff/merge review](ui/code_editor/user_docs/README.md)
- [Archive contents and previews](ui/archive_view/user_docs/README.md)
- [Shared text and INI editors](ui/user_docs/README.md)

## Contributing

Use the current import paths and [integration contracts](docs/developer/contracts.md).
There is no documented semantic
versioning or universal API stability promise. Test affected consumers before
updating pinned or vendored revisions. See [contributor guidance](AGENTS.md).

## License

[MIT](LICENSE.md). Copyright © 2020–2026 Marc-André Voyer.
