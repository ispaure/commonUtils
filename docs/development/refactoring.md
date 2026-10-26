# Refactoring commonUtils safely

This guide records the October 25, 2026 review at `b105857d` and explains how to
choose the next shared-library change. It is a maintenance plan, not a promise
that an untested platform or consumer is supported.

## Keep the boundaries already implemented

`DirectoryCache` composes `DirectoryScan`; each writer owns a fresh `ScanState`.
Markdown composes document, formatted-editing, search and table state. Native
browsing shares `BrowserLifecycle` for epochs, task retirement and thumbnail
caches. Portable resource protocols live in `runtime.resources`, with Qt/native
presentation under `ui`. These are implemented owners, not a proposed rewrite.

The [readability record](readability.md), [architecture](architecture.md) and
[API map](public-apis.md) explain these contracts. Replacing composition with
forwarding mixins would hide dependencies again.

## Reuse existing bounded streams

Large-file consumers should use
[`runtime.streams.file_sha256`](../../runtime/streams/__init__.py) rather than
reading a complete file just to hash it. It reads bounded chunks and checks
cancellation. `copy_stream` handles short writes; `read_up_to` makes input bounds
explicit. The consumer chooses limits, destinations, approval and error display.

```python
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from commonUtils.runtime.streams import file_sha256

with TemporaryDirectory() as temporary:
    path = Path(temporary) / 'artifact.bin'
    path.write_bytes(b'example artifact')
    assert file_sha256(path) == sha256(b'example artifact').hexdigest()
```

Preserve digest encoding, byte order and missing-file behavior. An archive-tree
digest may include relative names as well as bytes; substituting a plain file
digest changes its meaning. A bounded helper alone does not move work off the GUI
thread. See the [stream reference](reference/runtime/streams/streams.md).

## Implemented follow-up: explicit reconciliation writer context

[`filesystem/index/store.py`](../../filesystem/index/store.py) still combines
cache-session access, folder scanning, exclusion repair, storage mutation and
queries. Reconciliation now captures an `IndexWriterContext` containing database,
generation and `ScanState` under `_operation_writer`. Metadata checks, target
selection and descendant validation receive it directly, without discovering
their current attempt through private cache state.

Public `get`, `peek`, snapshots and stored generations are unchanged. The cache
still owns scan/storage helpers; this extraction does not move all SQL. A direct
metadata fixture uses a collaborator without an active-operation attribute,
proving that this path's context is explicit.

Before expanding this boundary further, demonstrate unchanged cancellation checkpoints,
rollback, old-reader visibility, partial resume and metrics. Start with
`tests/index/`, then the affected consumer's browser/index tests. The completion
criterion is fewer implicit writer prerequisites with the same observable results.

## Decide removable-volume behavior before changing retention

An indexed path and a mounted storage identity are different things. Root and
generation lookup is path-based. Metadata fingerprints and mount exclusions do
not establish a complete policy for a disconnected drive, a different drive
mounted at the same path, or preserving offline search results.

This remains a design question from the [historical audit](audit.md). First agree
whether offline results remain visible, how they are labelled and when replacement
storage invalidates them. Add fixtures for disconnect/reconnect, replacement at
the same mount point and cancellation during reconciliation. This review did not
reproduce a data-loss defect. Do not silently introduce a schema migration as
part of a readability change.

## Extract native code by lifetime

`ui/native/navigation.py` contains Apple and Android adapters for containment,
overflow navigation, keyboard geometry and retirement. Construction factories
and callback retirement fixes are already implemented. Its length alone does
not justify another rewrite. If needed, isolate one lifetime, such as keyboard
observation, while retaining the exact install/dispose order.

Fake adapters check callback admission and state transitions. Native checks must
also cover overflow, repeated install/uninstall, keyboard appearance, inactive
windows, Android resize and late callbacks. The [native reference](reference/ui/native/native.md)
and [mobile test guide](mobile-testing.md) distinguish these checks. Offscreen or
dummy adapters do not certify physical pen, speech or OS-window behavior.

## A practical contribution loop

1. Choose a behavior and owning guide from the [API map](public-apis.md). Find
   real consumers before changing imports, signatures or return values.
2. Capture old behavior with disposable fixtures, including failure and close
   paths. Give each operation its own state.
3. Change one mechanism. Keep scheduling, application policy and software
   installation in the consumer; avoid a second facade or global cache.
4. Run focused shared tests in isolated processes where Qt lifetimes require it,
   followed by consumer checks using that consumer's interpreter.
5. Update the owning reference and user guide. Check wiki links and examples.
   Record unavailable native/service checks separately from passing host tests.

See [maintenance](maintenance.md), [integration contracts](contracts.md) and
[test selection](reference/tests/tests.md). Consumers have independent pins:
a Logistics pass does not update or validate the build manager's commonUtils copy.

[Developer documentation](development.md)

## Validation of this review

The focused shared selection passes 37 tests: wiki layout (3), bounded streams
(11), index writer state (3) and reconciliation (20). The new hashing example runs
against a disposable file with the Logistics consumer interpreter. All 81 shared
wiki pages pass H1, navigation and link checks. These focused checks support the
described contracts; they do not establish fresh native or external-consumer
acceptance for a future refactor.
