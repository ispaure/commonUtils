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
