# Virtual resource runtime

Import the specific owner below. `runtime.resources` itself imports no toolkit;
its former flat runtime modules have been removed. Update imports, deferred module
names and test patch targets together. No global module aliases are installed.

| Need | Module |
| --- | --- |
| Directory/archive protocols, capabilities and revision-bearing rows | `runtime.resources.provider` |
| Rooted ordinary local storage | `runtime.resources.local.LocalFiles` |
| Complete verified save, move, rename, folder creation and deletion | `runtime.resources.mutations` |
| Open/Save As selection, provider leases and text baselines | `runtime.resources.selection` |
| Portable slash-delimited identifier validation | `runtime.resources.paths` |
| Recursive provider queries | `search.providers` |
| Local streamed ZIP access | `runtime.resources.archives` |
| Bounded seekable range reads | `runtime.resources.range_reader` |
| Scoped local, iOS and Android document byte access | `runtime.resources.documents` |

## Identifier and storage boundaries

`resource_path(value)` converts to a string and accepts the empty root (`''` or
`'.'`) or slash-separated relative components. It rejects absolute paths,
backslashes, colons, characters below U+0020 and empty, dot or parent components.
`resource_name(value)` further requires one nonempty child component. Neither
function resolves physical paths or grants storage access. Providers retain
root containment, link rules, capabilities, revision and credential validation.
The `provider.resource_path` export refers to the same validator.

```python
from commonUtils.runtime.resources.paths import resource_path, resource_name

assert resource_path('.') == ''
assert resource_path('notes/chapter.md') == 'notes/chapter.md'
assert resource_name('chapter.md') == 'chapter.md'
try:
    resource_path('notes/../private.md')
except ValueError:
    pass
else:
    raise AssertionError('Parent traversal must be rejected')
```

See the [provider contract](../../ui/resource-providers.md) for mutation results,
revision checks, source leases and complete picker/editor integration. Atomic
publication lives in `persistence.publication`; transfer phase helpers live in
`persistence.transfers`. Applications own credentials, user confirmation,
recovery and the lifetime of private sources.

[Runtime guide](../runtime.md)

## Cache-backed local filename search

`search.indexed.IndexedLocalSearch(database, eligible=...)` composes the directory
index with resource-provider results. The host explicitly admits physical local
adapters and supplies the database location. Private, session-only and remote
providers always use memory-only recursive search, even if admitted by mistake.

Call `prepare(provider, directory, cancelled=...)` off the UI thread to reconcile
names, then `search(...)` for cached hits. A persisted hit is revalidated through
`provider.entry`; missing entries are skipped and access errors mark results
incomplete. Provider guards run before scanning and before results return. Cached
metadata never grants access to a file. Close `search.cache` after retiring its
workers. Query rules, symlink exclusion and stale-name behavior match directory
index search; applications own refresh scheduling and provider eligibility.

## Streamed mutations

Local file creation and mutation verification use the shared bounded stream
helpers. A read returning `None` raises `BlockingIOError` rather than completing
with truncated content. Failed local creation removes its own new file; failed
verification preserves the selected destination and cleans the private stage.

## Leases and worker cancellation

`lifetime.ResourceLeases(validate=..., close=...)` provides idempotent release
callbacks for multiple browser/document owners. Acquisition validates under a
reentrant lock; the last release calls `close` under that lock. Explicit closure,
credential revocation and cache clearing remain with the provider. A release
which raises during cleanup is still consumed and will not call cleanup twice.

`lifetime.WorkerCancellation` composes nested predicates in `scope(cancelled)`
and restores the outer predicate on every exit. Other threads remain independent.
Capture `current` to pass the current predicate to downstream work; reading it
on another thread selects that thread's scope. Neither class imports a UI toolkit
or establishes an application session policy.
