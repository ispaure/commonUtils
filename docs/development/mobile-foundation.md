# Mobile compatibility foundation

This is infrastructure, not an iOS/Android port or a mobile UI. Desktop contracts
remain Windows, macOS and Linux. Mobile assertions are simulated unless explicitly
recorded as device-verified below. No mobile device validation has been performed.

## Compatibility audit

Historical names osUtils, fileUtils, dirUtils, appUtils and pySideUtils correspond
to runtime/platform, filesystem/files, filesystem/directories,
integrations/applications and ui/pyside respectively in this checkout.

| Area | Finding / boundary |
| --- | --- |
| OS and architecture | OS enum had three desktop values plus UNKNOWN; unknown detection raises RuntimeError. Additive IOS/ANDROID values preserve existing strings and exceptions. Architecture remains independent. |
| OS path selection | Three existing path arguments cannot represent mobile paths. Keep signature and reject mobile explicitly; hosts supply sandbox paths directly. |
| Files/directories | Local path, copy, traversal and text operations are useful without desktop integration. Unused eager pwd import and command imports should be removed/deferred; opening a directory must not fall through to xdg-open on mobile. |
| Applications/commands | Three-way launch switches can silently do nothing; POSIX identity does not prove subprocess or desktop shell support. Guard adapter entry points. |
| UI/PySide | Generic facade already loads backends lazily. Explicit PySide imports require Qt. Font/application setup, desktop dialogs, menus, Cocoa and keyboard adapters are desktop components, not a mobile UI contract. |
| Document data | Registry, text persistence, Markdown source and ZIP reading should be usable separately from preview widgets, legacy archive progress UI and external tools. EPUB/CBZ packaging/reader UI remains consumer-owned. |
| Storage/configuration | Desktop default cache/settings paths are not mobile sandbox locations. Mobile callers must supply explicit paths; automatic desktop fallback must fail before creating directories. |
| Native checks | Windows reparse points, ctypes, native menus and Cocoa bridges are intentionally platform-specific. POSIX rename/permission/locking semantics are not evidence of mobile deployment readiness. |
| Index/network | Desktop mount-table probes and process coordinators require separate policy; do not treat older Android as Linux mount integration. Locks, SQLite and background runners need device validation. |
| Other adapters | Steam, Perforce, DMG, installers, launchers, speech, trash, archive executables and downloaded tools remain desktop integrations; no mobile support implied. |

The audit examined get_os/get_arch/get_os_path, all OS enum uses, sys.platform,
os.name and platform.system checks. os.name checks for filesystem semantics remain
valid as implementation choices, not capability declarations. Exact desktop checks
in native UI remain desktop-only. Unknown platforms still raise rather than
silently receiving Linux behavior from the central detector.

## Detection contract

`get_os()` returns `OS.IOS` ("iOS") or `OS.ANDROID` ("Android") in addition to the
unchanged desktop members. Android detection prioritizes `sys.platform ==
'android'`, then the Android-only `sys.getandroidapilevel` marker on older Linux-
identifying builds. iOS uses `sys.platform == 'ios'`; older Darwin-identifying
builds reporting iOS/iPadOS through platform.system are also recognized. Ambiguous
custom interpreters reporting only desktop identifiers need host integration;
environment variables alone are deliberately not trusted as device identity.

References: [CPython platform identifiers](https://docs.python.org/3/library/sys.html#sys.platform),
[Android runtime marker](https://docs.python.org/3/library/sys.html#sys.getandroidapilevel),
[iOS runtime](https://docs.python.org/3/using/ios.html).

## Remaining deployment blockers

- Choose/package an embedded interpreter and required binary dependencies for each
  mobile architecture; the consumer's desktop dependency set is not a mobile set.
- Supply app-private storage roots and document-provider/security-scoped access;
  Android content URIs are not pathlib paths. Validate permissions, atomic saves,
  encodings, ZIP/EPUB/CBZ handling and SQLite on actual devices.
- Implement and verify mobile adapters for document selection, external URLs,
  lifecycle/background work and any supported process operations.
- Select a mobile UI framework and port only needed presentation components in a
  future project. Qt desktop widgets are not certified for either mobile OS.
- Validate sandbox entitlements, signing, packaging, distribution and recovery
  after suspension/termination. Verify desktop native integrations on Windows and
  Linux in addition to the local macOS regressions.

## Implemented foundation and integration policy

`runtime.platform.capabilities` centralizes adapter policy for subprocesses,
shell integration, external applications, desktop UI/file dialogs and default
storage. IMPLEMENTED means an existing desktop adapter, not a successful runtime
probe. Mobile adapters are UNAVAILABLE; local filesystem access is UNVERIFIED on
all platforms until an operation is attempted. `probe_filesystem` reports VERIFIED
only for the actual path/read or temporary-file write it performed. See the
[API contract](reference/runtime/platform/platform.md#capability-policy).

Command entry points, application/URI launchers, directory opening and default
text editing reject mobile requests with `UnsupportedCapabilityError` before
side effects. The UI facade/native dialogs and explicit PySide import reject
mobile desktop UI use before Qt initialization; existing Qt file-dialog exports
remain part of that desktop-only facade. A mobile host must supply presentation
and document-selection adapters in future work. Critical diagnostics still raise
`DebugException` on mobile without attempting a desktop popup. Windows console
ANSI initialization is deferred until logging, preserving import-only use.

File/Directory/registry, text persistence, Markdown properties and plain ZIP
operations can be imported without Qt, pwd, ctypes or pyzipper. File permission
changes on caller-supplied mobile paths use native chmod and propagate permission
errors; this is not a sandbox escape or a promise that chmod succeeds. Plain ZIP
access uses stdlib zipfile; encrypted ZIP operations require pyzipper and report a
clear missing-dependency error. EPUB/CBZ tests exercise container I/O, not format
rendering, DRM, document-provider URIs or a complete reader.

On mobile, set `COMMONUTILS_STORAGE_ROOT` to an absolute app-private filesystem
path before importing the directory index or using automatic caches. Cache/Temp
subdirectories are resolved beneath it; `create=False` does not create them.
The override also works on desktop and disables legacy cache migration. Without
it mobile automatic storage fails explicitly instead of choosing desktop paths.
The index singleton resolves its default path at import; mobile hosts must set
this root first. Register an explicit personal settings path with
`configuration.layered.register_settings` before `shared_settings()` on mobile.
All paths still need actual runtime permission validation.

Desktop-only adapters outside these shared entry points are not a mobile API.
Direct platform integrations (for example DMG, Perforce, native widgets, external
archive programs and process-based index owners) still require separate review
when selected for a mobile application. No global override claims them supported.

## Validation evidence

The baseline commonUtils suite passed on the local macOS host: 717 tests, two
platform skips. Five-platform detection/capability matrices use mocks. Fresh
interpreter tests block optional desktop dependencies and exercise File/Directory,
Markdown/text and ZIP container operations on host temporary files under simulated
Windows/macOS/Linux/iOS/Android and legacy Android identities. They check that
imports neither initialize a GUI nor execute a shell. Boundary tests check mobile
errors before launching processes, sandbox root requirements and popup-free
critical errors. Actual Windows, Linux, iOS and Android runtime validation remains
outstanding; native dialogs and external programs are not exercised by mocks.

Final foundation validation on 2026-10-12: the isolated commonUtils suite completed
724 tests across 98 modules with zero failing modules (two platform skips). The
new portability module passed all eight tests separately; the combined detection,
capability and portability run passed 15 tests. Changed Python files also passed
the consumer's Ruff correctness configuration. The existing local ui/settings.ini
edit was excluded from all foundation commits. Logistics consumer regressions are
run before updating its submodule pin; no mobile-device or native Windows/Linux
success is inferred from these results.

The [manual embedded-runtime test harness](mobile-testing.md) passed all seven
cases on both a hosted Android emulator and iOS Simulator on 2026-10-12 at
`8ff459a`. The linked guide records exact revisions, runtime reports and the
initial iOS packaging failure and fix. Physical devices remain unverified; the
capability policy above remains unchanged.
