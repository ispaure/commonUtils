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

The project using commonUtils installs the packages it needs. Requirements vary
by module; there is no single install command for every tool.

| What you're using | What you need |
| --- | --- |
| Desktop widgets, file browser and Qt workers | `PySide6` |
| Shared ZIP tools and built-in file-type registration | `pyzipper` |
| External archive extraction | `patool`, plus a system extractor for the format |
| EXIF tools | `piexif` |
| Platform-specific tools | The relevant application or system command, such as PowerShell, `hdiutil` or Flatpak |

INI parsing and typed-setting validation use Python's standard library. Their
visual editor also needs `PySide6`. Some modules load dependencies when imported;
for example, built-in file-type registration loads ZIP support. See the
[dependency and platform notes](DEVELOPMENT.md#optional-dependencies-and-platforms)
for details. Create a `QApplication` before using Qt widgets; standalone scripts
can use the native dialog backend instead.

## Guides

| Looking for… | Start here |
| --- | --- |
| A file browser with your own actions and previews | [Browser features](FEATURES.md) |
| INI settings and their editor | [Configuration guide](configuration/README.md) |
| Examples of background work, downloads and cancellation | [Recipes](RECIPES.md) |
| Batch renaming | [Rename tools](RENAME.md) |
| File formats and custom file types | [File types](fileTypes/README.md) |
| ZIP archives | [Archive guide](ZIP_ARCHIVES.md) |
| XML documents | [XML guide](XML.md) |
| Desktop widgets and readers | [UI guide](ui/README.md) |
| Commands and processes | [Command wrapper](wrappers/cmdShellWrapper/README.md) |
| Module details, behavior and tests | [Developer reference](DEVELOPMENT.md) |

## License

[MIT](LICENSE.md). Copyright © 2020–2026 Marc-André Voyer.
