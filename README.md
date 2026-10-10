# commonUtils

commonUtils is a collection of Python tools shared by Logistics and Blue Hole. It helps with files, configuration, archives, background tasks and
desktop interfaces, so each project can focus on its own features.

It's a library to use in your code, rather than an app you open on its own.
It supports Windows, macOS and Linux; some tools are platform-specific.

## What can it do?

- **Files and folders:** browse, search, copy, move, rename and inspect files.
- **File formats:** read and write text, CSV, JSON, INI, XML and Markdown.
- **Configuration:** safely edit INIs, validate optional typed settings and show
  them as section tabs with editable fields.
- **Archives:** create, inspect, extract and verify ZIPs, including encrypted ZIPs;
  use external tools for other supported archive formats.
- **Desktop interfaces:** add file browsers, previews, dialogs, readers and storage charts.
- **Background work:** show progress and support cancellation for long tasks.
- **Downloads and streams:** copy or hash data and verify downloaded files.
- **System tools:** run commands, work with links and open files or applications.

## Use it in your project

You'll need **Python 3.10 or newer**. Put this repository in a folder named
`commonUtils` beside your Python code, or add it there as a Git submodule. Its
parent folder must be on Python's import path. There isn't a pip-installable
package for this repository yet.

For example:

```text
my_project/
└── Python/
    ├── launch.py
    └── commonUtils/
```

A small example you can use in `launch.py`:

```python
from commonUtils.formats.jsonType import JSONFile

settings = JSONFile("settings.json")
settings.write_json({"enabled": True})
print(settings.read_json())
```

For Git submodules, run `git submodule update --init --recursive` after cloning.
See the [developer reference](docs/DEVELOPMENT.md#use-it-in-a-project) for import-path
setup and more examples. If you're using Logistics, its launcher handles setup.

## Dependencies

Consumers install the optional dependencies required by their chosen modules.
See [development and platform setup](docs/DEVELOPMENT.md#optional-dependencies-and-platforms)
and each area's README for specific requirements.

## Guides

| Looking for… | Start here |
| --- | --- |
| A file browser with your own actions and previews | [Browser features](docs/FEATURES.md) |
| INI settings and their editor | [Configuration guide](configuration/README.md) |
| Examples of background work, downloads and cancellation | [Recipes](docs/RECIPES.md) |
| Batch renaming | [Rename tools](docs/RENAME.md) |
| File formats and custom file types | [File types](formats/README.md) |
| Archive operations | [Archives](archives/README.md) |
| XML documents | [XML guide](docs/XML.md) |
| Desktop widgets and readers | [UI guide](ui/README.md) |
| External tools and processes | [Wrappers](integrations/wrappers/README.md) |
| Directory indexing | [Directory](filesystem/index/README.md) |
| Atomic publication, text and recovery | [Persistence](persistence/README.md) |
| Project bootstrap scripts | [Launchers](launchers/README.md) |
| Regression tests | [Tests](tests/README.md) |
| Module details, behavior and tests | [Developer reference](docs/DEVELOPMENT.md) |

## Package map

| Area | Responsibility |
| --- | --- |
| [filesystem](filesystem/README.md) | Files, folders, links, transfers, removal, traversal, indexing and storage |
| [formats](formats/README.md) | File types, JSON, INI, XML, Markdown and spreadsheets |
| [archives](archives/README.md) | Archive creation, reading, editing and extraction |
| [runtime](runtime/README.md) | Platform support, diagnostics, logging, operations and streams |
| [integrations](integrations/README.md) | Applications, web links, Steam and command wrappers |
| [configuration](configuration/README.md) | Schemas, settings and legacy config helpers |
| [persistence](persistence/README.md) | Atomic publication, sessions, text recovery and merging |
| [ui](ui/README.md) | Desktop widgets, file browsers, readers and feature declarations |
| [launchers](launchers/README.md) | Project bootstrap scripts |
| [tests](tests/README.md) | Shared regression tests |
| [docs](docs/ROOT_LAYOUT.md) | Architecture, developer guides and recipes |

Use these canonical paths for new code. Historical paths are lazy aliases defined
in `_compat.py`; they share the canonical modules, classes and state. Both
Logistics and Blue Hole use the same implementation.

## License

[MIT](LICENSE.md). Copyright © 2020–2026 Marc-André Voyer.
