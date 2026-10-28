# Native iOS widget value components

`ui/native/ios/WidgetValueStore.swift` and `WidgetValueView.swift` are native source
components for lightweight extensions. Compile the source files into a consumer's
native targets; they are not Python modules and do not load a toolkit or app host.
The consumer owns widget kinds, app intents, app groups, signing, target creation,
names, input routing and refresh policy.

## Snapshot storage

`WidgetValueStore(appGroup:)` resolves an explicitly supplied entitled app-group
container. `WidgetValueStore(container:)` accepts a caller-owned container for
isolated fixtures. No fallback into personal or global storage is attempted.
Storage lives in `WidgetValues/` below that container.

`set(name:title:value:now:)` atomically publishes a Codable `WidgetValueRecord`
with title, value and update date. It returns false for unchanged title/value,
preserving the prior date and avoiding a write. Consumers can then skip their
widget reload request. Concurrent writes replace complete records; this is
last-writer-wins storage, not a counter increment or compare-and-swap service.

`read(name:)` returns nil for a missing record and throws for invalid, malformed
or inaccessible storage. It never rewrites data. Explicit set can repair a
malformed old record. Each name maps to a SHA-256 filename, so caller-supplied
slashes cannot escape the owned directory. Names are exact and case-sensitive;
empty/whitespace-only names and names longer than 64 characters are rejected.
Titles allow up to 64 characters, values 512; encoded records are capped at 8192
bytes. Reads inspect file size before decoding and reject excessive content.

iOS atomic writes use complete-until-first-user-authentication protection, so a
native extension can access explicitly shared display values while the phone is
locked after the first unlock. The record contains no application credentials,
schema discovery, cloud sync, timer, network transport or directory enumeration.
Consumers decide backup/deletion policy and whether their supplied values are
appropriate for a publicly visible widget. Removing a widget does not delete data.

## Presentation

`WidgetValueView(title:value:detail:)` renders a compact accessible SwiftUI value
with a secondary title, rounded monospaced-digit value, optional detail and
bounded line counts/scaling. It performs no I/O or scheduling. The consumer
supplies container background, widget family, privacy marking and missing/error
presentation. Build the view with SwiftUI on an Apple platform.

## Validation

`tests/native/WidgetValueStoreChecks.swift` is a native executable fixture. Compile
it with the store source using `swiftc -parse-as-library`, then supply a disposable
container path. It checks persistence between independent instances, unchanged
writes/dates, name isolation, traversal containment, bounds and corrupt-record
recovery. The consumer should use its own managed scratch/build lifecycle.
Native consumer packaging and Shortcuts/widget invocation need separate platform
validation; a passing storage fixture does not establish widget refresh latency.
