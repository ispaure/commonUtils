# Runtime

Cross-cutting mechanisms used by the filesystem, archives, UI and applications.
Import the specific module you need; importing this area loads no GUI backend.

- `platform`: OS detection and platform constants.
- `diagnostics`: logging, severity and scoped debug settings.
- `logging`: timestamp helpers.
- `operations`: progress events and cooperative cancellation.
- `streams`: bounded copying, hashing and verified downloads.
- `helpers`: small shared helpers.
- [updates](updates/README.md): branch/release discovery, protected installation transactions and detached restart.

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
can remain platform-specific. Route platform choices through `runtime.platform` and consult
the relevant module before relying on an external tool.

```python
from commonUtils.runtime.platform import get_os, get_arch, OS

if get_os() == OS.WIN:
    print('Windows-specific workflow')
print(get_arch())
```

## Virtual resource streams

`resource_provider` defines structural directory and archive source contracts;
`range_reader.RangeReader` supplies bounded seekable reads without disk caching.
See [resource provider contracts](../ui/resource-providers.md) for revisions,
cancellation, staging verification and ownership.

`local_files.LocalFiles` implements rooted storage, while `resource_mutations`
owns complete verified save/move/delete operations. Providers declare
`ResourceCapabilities`; mutation results live in `operations`. Atomic publication
and the shared save transaction belong to `persistence.publication`.

`browsing` supplies portable, bounded entry/column snapshots and an identity-based
container tree for UI adapters. It requires neither filesystem paths nor a GUI
toolkit; see the [browsing contract](../ui/resource-providers.md#shared-item-presentation).


`browsing.BrowseHistory` owns bounded opaque navigation locations; `query_entries`
filters and naturally sorts loaded snapshots without storage access.
`archive_source.LocalArchiveSource` provides revision-checked local ZIP streaming
and bounded member reads without an overall archive-size limit. Formats and hosts
choose buffer/header limits and retain domain validation.

## Optional device-protected keys

`protected_keys.AndroidKeys(alias_prefix=..., aad_prefix=...)` wraps 32-byte
keys using AndroidKeyStore AES-GCM. `IOSKeys(service=..., label=...,
label_prefix=...)` stores 32-byte keys in unlocked/device-only, non-synchronizing
Keychain items. Native dependencies load only when constructing the relevant
adapter. Missing/inaccessible keys raise `KeyStoreUnavailable`; no plaintext
fallback is provided. Hosts own namespace constants, backup exclusions, metadata
records and encrypted payloads. Changing a namespace/AAD string makes existing
keys inaccessible; preserve those strings during consumer migrations.
