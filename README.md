# commonUtils

commonUtils is a collection of Python tools shared by Logistics and other
projects. It helps with files, configuration, archives, background tasks and
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
from commonUtils.fileTypes.jsonType import JSONFile

settings = JSONFile("settings.json")
settings.write_json({"enabled": True})
print(settings.read_json())
```

For Git submodules, run `git submodule update --init --recursive` after cloning.
See the [developer reference](DEVELOPMENT.md#use-it-in-a-project) for import-path
setup and more examples. If you're using Logistics, its launcher handles setup.

## Dependencies

Consumers install the optional dependencies required by their chosen modules.
See [development and platform setup](DEVELOPMENT.md#optional-dependencies-and-platforms)
and each area's README for specific requirements.

## Guides

| Looking for… | Start here |
| --- | --- |
| A file browser with your own actions and previews | [Browser features](FEATURES.md) |
| INI settings and their editor | [Configuration guide](configuration/README.md) |
| Examples of background work, downloads and cancellation | [Recipes](RECIPES.md) |
| Batch renaming | [Rename tools](RENAME.md) |
| File formats and custom file types | [File types](fileTypes/README.md) |
| Archive operations | [Archives](archives/README.md) |
| XML documents | [XML guide](XML.md) |
| Desktop widgets and readers | [UI guide](ui/README.md) |
| External tools and processes | [Wrappers](wrappers/README.md) |
| Directory indexing | [Directory](directory/README.md) |
| Atomic publication, text and recovery | [Persistence](persistence/README.md) |
| Project bootstrap scripts | [Launchers](launchers/README.md) |
| Regression tests | [Tests](tests/README.md) |
| Module details, behavior and tests | [Developer reference](DEVELOPMENT.md) |

## Package map

See [root layout decisions](ROOT_LAYOUT.md) for the relocation rationale.

- [appUtils](appUtils/README.md)
- [archives](archives/README.md)
- [configuration](configuration/README.md)
- [debugUtils](debugUtils/README.md)
- [dirUtils](dirUtils/README.md)
- [directory](directory/README.md)
- [downloads](downloads/README.md)
- [features](features/README.md)
- [fileTypes](fileTypes/README.md)
- [fileUtils](fileUtils/README.md)
- [file_operations](file_operations/README.md)
- [file_removal](file_removal/README.md)
- [filesystem](filesystem/README.md)
- [launchers](launchers/README.md)
- [linkUtils](linkUtils/README.md)
- [logUtils](logUtils/README.md)
- [marcUtils](marcUtils/README.md)
- [markdownUtils](markdownUtils/README.md)
- [network_filesystems](network_filesystems/README.md)
- [operations](operations/README.md)
- [osUtils](osUtils/README.md)
- [persistence](persistence/README.md)
- [renameUtils](renameUtils/README.md)
- [settings](settings/README.md)
- [spreadsheetUtils](spreadsheetUtils/README.md)
- [steamUtils](steamUtils/README.md)
- [storage](storage/README.md)
- [streams](streams/README.md)
- [tests](tests/README.md)
- [traversal](traversal/README.md)
- [ui](ui/README.md)
- [webUtils](webUtils/README.md)
- [wrappers](wrappers/README.md)
- [zipUtils](zipUtils/README.md)
- [zip_access](zip_access/README.md)

## License

[MIT](LICENSE.md). Copyright © 2020–2026 Marc-André Voyer.
