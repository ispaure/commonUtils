# Runtime

Cross-cutting mechanisms used by the filesystem, archives, UI and applications.
Import the specific module you need; importing this area loads no GUI backend.

- `platform`: OS detection and platform constants.
- `diagnostics`: logging, severity and scoped debug settings.
- `operations`: progress events and cooperative cancellation.
- `streams`: bounded copying, hashing and verified downloads.
- [updates](updates/updates.md): branch/release discovery, protected installation transactions and detached restart.

Example: `from commonUtils.runtime.operations import check_cancelled`.

[Library overview](../../overview.md).

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

`resources.provider` defines structural directory and archive source contracts;
`resources.range_reader.RangeReader` supplies bounded seekable reads without disk caching.
See [resource provider contracts](../ui/resource-providers.md) for revisions,
cancellation, staging verification and ownership.

`resources.local.LocalFiles` implements rooted storage, while `resources.mutations`
owns complete verified save/move/delete operations. Providers declare
`ResourceCapabilities`; mutation results live in `operations`. Atomic publication
and the shared save transaction belong to `persistence.publication`.

`browsing` supplies portable, bounded entry/column snapshots and an identity-based
container tree for UI adapters. It requires neither filesystem paths nor a GUI
toolkit; see the [browsing contract](../ui/resource-providers.md#shared-item-presentation).


`browsing.BrowseHistory` owns bounded opaque navigation locations; `query_entries`
filters and naturally sorts loaded snapshots without storage access.
`resources.archives.LocalArchiveSource` provides revision-checked local ZIP streaming
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

## Portable speech sessions

`speech.utterances(text, start=0, end=None, limit=1000, breaks=())` yields
`(text, start, end)` with UTF-16 code-unit offsets. The session never reads a
book, document, preference store or UI. `SpeechSession(engine, on_range=...,
on_state=..., clock=...)` queues bounded utterances and rejects retired generation
callbacks. Engines supply `ready`, `error`, `speak(text, voice, speed, token)`,
`stop()` and `close()`, and receive `started`, `progress`, `completed` and `failed`
callbacks. An optional engine loop schedules approximate word progress.
`can_speak` is a caller-supplied gate checked before each utterance.

`PlaybackTimer(loop, changed=..., expired=..., clock=...)` tracks active listening
time. Pause preserves the remaining budget; Play after expiry starts a fresh
budget. `dispose()` cancels outstanding timer handles. The host owns source text,
selection, saved voice preferences, privacy gating and when to dispose a session.
Qt read-aloud also uses `SpeechSession` and `PlaybackTimer`;
`ui.readers.qt_speech` adapts Qt scheduling and engine callbacks. Each platform
retains its own widgets, voice selection and installed-engine availability.

`speech_language.passage_language(text, hint='')` detects up to 6,000 characters
locally with optional `langdetect==1.0.9` profiles. Detection uses a deterministic
seed, at least 20 letters and a probability threshold of 0.85; uncertain text
falls back to the supplied language tag. Only profiles are cached, never text.
`matching_locale(language, locales, preferred='')` selects an offered locale,
preferring an exact tag or a compatible preferred dialect. No match returns an
empty string. Consumers own dependency installation and missing-voice UI.

## Coalesced async signals

`signals.CoalescedSignal` broadcasts without timers or retained owners. Call
`waiter(initial=True)` for each subscriber, await its returned closure, and call
`notify()` on the owning loop thread. A burst becomes one wakeup per subscriber;
notifications arriving before a wait are preserved. `initial=False` waits for the
first notification. Cancel in-flight waits and release the closure on retirement.

The [resource module map](resources/resources.md) lists canonical imports and
identifier validation. Former flat resource modules have been removed.

Search mechanisms live in [search](../search/search.md); personal filesystem defaults belong to consumers.

## Pages

- [Diagnostics and error presentation](diagnostics/diagnostics.md)
- [operations](operations/operations.md)
- [Operating system and architecture](platform/platform.md)
- [streams](streams/streams.md)


## Ordered choices

`choices.ChoiceOption(id, label)` is an immutable option. `ChoiceSet(options)`
snapshots an ordered collection with unique hashable IDs; duplicate IDs raise
`ValueError`. `None` is an ordinary ID with no automatic/empty-selection meaning
assigned by this collection. Selection and unknown-ID policy belong to callers.

The collection supports iteration, indexing/slicing, `labels`, `by_id(id)` and
`index_of(id)`. Missing identities raise `KeyError`. Labels can repeat, so a native
control capable of retaining IDs should do so. String-only bindings can use
`from_label(label)`: unknown labels raise `KeyError`, ambiguous labels raise
`ValueError`. Renaming or reordering options does not change their identities.
There are no callbacks, widgets, task runners or persistence in this contract.
