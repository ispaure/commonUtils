# Operating system and architecture

Import from `commonUtils.runtime.platform`. Implementation and public exports live in
[`__init__.py`](../../../../runtime/platform/__init__.py).

Public entry points: `OS`, `get_os`, `Arch`, `get_arch`, `get_os_path`

[Library overview](../../../overview.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `get_os_path` | Returns the correct path based on the current operating system. |

`OS.IOS` and `OS.ANDROID` are additive enum members. `get_os()` recognizes modern
mobile interpreter identifiers and legacy runtime markers before desktop checks.
Unknown platforms still raise `RuntimeError`. `get_os_path(path_win=None,
path_mac=None, path_linux=None)` keeps its desktop-only signature and raises on
mobile; callers must supply their own sandbox paths. See the
[mobile audit](../../../developer/mobile-foundation.md).

## Capability policy

`runtime.platform.capabilities` exports `Capability`, `CapabilityState`,
`CapabilityStatus`, `capability_status`, `require_capability`,
`UnsupportedCapabilityError`, `sandbox_restrictions` and `probe_filesystem`.
Queries perform no GUI, process or filesystem initialization. Desktop adapter
status is IMPLEMENTED, not VERIFIED: installed dependencies and runtime access
still matter. Mobile desktop adapters are UNAVAILABLE until separately verified;
`require_capability` raises a descriptive RuntimeError subclass before use.

Filesystem access is UNVERIFIED globally on every OS. `probe_filesystem(path)`
actually opens a file or lists a directory. `write=True` requires a directory and
creates/removes its own temporary file. VERIFIED applies only to that probe and
path at that moment; perform the real operation and handle its errors as usual.
`sandbox_restrictions()` returns True for mobile and None for desktop (unknown),
never an unsupported promise of unrestricted desktop access. There is no global
"enable mobile support" override; future integrations need explicit adapters.

`register_qt_ui_host(application)` admits only `Capability.QT_UI` for a live
Qt 6.12+ QApplication supplied on its GUI thread. Register before importing
`ui.pyside` on mobile. This reports IMPLEMENTED, not VERIFIED; exercise each
component on the target runtime. Desktop UI, file dialogs, default storage,
shell commands and external application launching remain unavailable on mobile.
Supply explicit private storage and personal settings paths. The registration
holds only a weak reference and stops admitting Qt when its host is destroyed.
