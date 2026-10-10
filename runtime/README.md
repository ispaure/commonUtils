# Runtime

Cross-cutting mechanisms used by the filesystem, archives, UI and applications.
Import the specific module you need; importing this area loads no GUI backend.

- `platform`: OS detection and platform constants.
- `diagnostics`: logging, severity and scoped debug settings.
- `logging`: timestamp helpers.
- `operations`: progress events and cooperative cancellation.
- `streams`: bounded copying, hashing and verified downloads.
- `helpers`: small shared helpers.

Example: `from commonUtils.runtime.operations import check_cancelled`.

[Library overview](../README.md).

## Optional dependencies and platforms

The consuming application manages dependencies. Importing a module may require
its own extras; this repository does not supply one exhaustive install command.

| Capability | Requirements |
| --- | --- |
| Qt browser, workers and PySide UI | `PySide6`; create one QApplication before widgets |
| ZIP operations | `pyzipper`; archive metadata can be imported without it |
| External archive/RAR extraction | `patool` (`patoolib` import) and format-specific system extractors |
| EXIF wrapper | `piexif` |
| Platform workflows | Relevant system tools, such as PowerShell, `hdiutil` or Flatpak |

Windows, macOS and Linux are supported at the library level; individual operations
can remain platform-specific. Route platform choices through `osUtils` and consult
the relevant module before relying on an external tool.

```python
from commonUtils.runtime.platform import get_os, get_arch, OS

if get_os() == OS.WIN:
    print('Windows-specific workflow')
print(get_arch())
```
