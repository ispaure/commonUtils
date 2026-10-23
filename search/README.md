# Shared search

Search owns reusable query/matching and traversal mechanisms. Widgets, document
selection, highlights, debounce timers and worker lifetime stay under `ui/`.
Consumers choose roots, exclusions, private-storage policy and buffer snapshots.

| Module | Responsibility | Dependencies |
| --- | --- | --- |
| `names` | Filename keyword/quoted-phrase rules, in-memory matching and SQLite predicates | Standard library |
| `text` | Literal editor patterns and casefolded catalog substring matching | Standard library |
| `providers` | Bounded, cancellable recursive name search over rooted providers | Portable runtime |
| `indexed` | Explicitly admitted local providers backed by the filesystem metadata index | Filesystem/runtime |
| `qt_text` | Bounded PCRE Find/Replace matching with UTF-16 offsets | PySide6 QtCore; no widgets/application |
| `files` | Text-content search across supplied roots and unsaved buffers, plus bounded preview reads | QtCore loaded only when searching |

Filename indexes contain names and metadata, not document contents. Provider
search validates every returned path against its scope; indexed hits are rechecked
through the provider. Private/session/remote providers are never automatically
admitted to persistent local indexes.

`files.search_files(roots, excluded, query, masks='', *, case=False, whole=False,
regex=False, buffers=None, cancelled=..., limit=500, max_files=10000,
max_entries=100000, max_file_size=1048576)` returns immutable hits with paths,
line numbers, code-point columns, UTF-16 offsets and bounded excerpts. These
options are keyword-only after `masks`. Roots/options/buffers belong to the caller;
pass stable snapshots from a worker. Searches skip symbolic links and unreadable,
non-text or oversized files. `limited` reports traversal/match/result caps;
cancellation returns no hits. Buffer text overrides disk bytes without saving.
`preview_text(path, buffer=None)` reads up to 1 MiB or returns the supplied buffer.

`qt_text.find_matches` retains desktop PCRE syntax, replacement capture expansion,
selection scope, Unicode word rules, cooperative cancellation and a 50,000-match
cap. Its offsets are UTF-16 units for Qt; native Python text operations use code
points. Native rendered Markdown uses DOM ranges and retains its own matching
adapter. These engines deliberately keep their established semantics.

## Presentation owners

- [Code editor](../ui/code_editor/README.md): desktop Find/Replace and highlights.
- [Markdown](../ui/markdown/README.md): wiki library search and current-page marks.
- [File Browser](../ui/file_browser/README.md): cached recursive filename results.
- [Resource windows](../ui/resources/README.md): provider search presentation.
- [Native components](../ui/native/README.md) and [browser](../ui/native_browser/README.md): platform selection, DOM ranges and native browsing.

Markdown catalogs remain in `formats.markdown.wiki`: catalog construction and
folder landing conventions belong to Markdown, while substring matching is shared.
SQLite readers remain in `filesystem.index` and consume `search.names` directly.
Logistics' IDE owns the Find in Files dialog and project options; `search.files`
owns the reusable traversal and matching.

## Import migration

Use direct imports from this package. Removed paths are `search.names`,
`search.providers`, `search.indexed` and the
`filesystem.index.search` forwarding module. Import `find_matches` from
`search.qt_text`, not the editor widget module. Logistics' former
`features.ide.ui.project_search` implementation now lives in `search.files`.
No global aliases are installed; vendored namespaces remain independent.

[Library overview](../README.md) · [Public API map](../docs/developer/public-apis.md)
