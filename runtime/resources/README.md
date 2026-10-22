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
| Recursive provider queries | `runtime.resources.search` |
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

[Runtime guide](../README.md)
