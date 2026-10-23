# Virtual resource providers

Providers let a host reuse browsing and document presentation without exposing a
normal filesystem. The library owns no account, encryption, remote routing or
credential policy. Structural types live in `runtime/resources/provider.py`;
implementers need not inherit them.

## Directory browsing

Provider rows may include `hidden: bool` for native hidden metadata. `LocalFiles`
sets it from dot names and the filesystem's Hidden/UF_HIDDEN flags during entry
loading. The continuous native browser also recognizes dot-prefixed leaf names
for providers without this field, and passes the state to recycled list rows and
tile captions. Rendering does not probe provider paths for hidden metadata.

`ResourceBrowser(provider, parent=None, directory=None, actions=(), thumbnail=None)` uses the
`DirectoryProvider` contract:

- `root: Path` is a virtual namespace root, not a promise of readable disk files.
- `relative(path)` validates an absolute virtual path or relative string and returns
  a slash-separated path inside the provider. Reject traversal and escapes.
- `list(path='', cancelled=callback)` returns dictionaries containing `name`,
  `path` (relative to root), `directory` (bool), `size` (bytes; ignored for folders),
  and `modified` (display text). Reject invalid names before publishing rows.

Listing runs on a worker. It must not access widgets and must honor the cancellation
callback. Activation emits `root / row['path']`; custom actions receive that same
virtual path. Consumers must use provider I/O, never implicit filesystem fallback.
The widget keeps navigation and filtering in memory; it builds no persistent index,
thumbnail store or recent-file history. Compact navigation buttons and breadcrumbs
share the regular browser's drawing; breadcrumb icons are generic and never probe
virtual paths on disk. `breadcrumbs.paths` contains only the root and its logical
descendants. The shared list, tile and column views remain independent of previews and storage-map modes.
Hosts own the provider's lifetime.
`stop()` requests cancellation and returns true while work remains; retain the
widget and provider until `idle` and retry closure.

## Seekable archives and replacements

`ArchiveSource.version(path)` returns an equality-comparable revision token.
`open(path)` is a context manager yielding a seekable binary reader. Validate
revisions during reads where underlying content can change. `RangeReader` adapts
bounded `(offset, count) -> bytes` callbacks into such a reader: callbacks must
return exactly the requested byte count. Its default cache is eight 1 MiB blocks;
a single read is limited to 128 MiB. Closing clears cached blocks. It creates no
disk cache. Sources own any additional whole-document/member limits.

`WritableArchiveSource.replace_stream(path, writer, expected_revision=token,
verify=None)` gives `writer` a binary output stream. Stage changes without replacing
the original. If supplied, `verify(virtual_staged_path)` reopens the staged resource
through the same source and raises on failure. Recheck the expected revision and
cancellation before atomic publication; failure must preserve the original and
clean temporary output. Atomic replacement does not provide a cross-process lock.
Cancellation after publication cannot undo a completed replacement. A provider may
supply an operation scope rather than adding cancellation arguments to every method;
that scope must remain local to the worker and propagate into writer callbacks.

## Markdown storage

Pass `storage=` to `MarkdownViewer` or `MarkdownWindow`. The adapter supplies
`read_bytes(path)`, `write_bytes(path, data, expected=original_bytes)`,
`load_resource(kind, url)` and `open_link(path, fragment)`. Resource loading happens
on the GUI thread: prefetch on a worker and serve bounded memory content there.
Do not let missing resources fall back to local files or network access.

Optional `submit_write(path, data, expected, completed)` schedules asynchronous
saves. Invoke `completed(error)` on the GUI thread after worker retirement, with an
empty error on success. Retain the window during writes; close requests can be
vetoed/deferred. `private=True` disables persistence-sensitive viewer actions,
including temporary-file diagram rendering. Save As is disabled unless the storage
adapter explicitly supplies `save_as(viewer)`, which owns destination selection,
publication, editor retargeting and provider lifetime. This flag is a UI policy
hook, not encryption or a guarantee of memory zeroization. The host is responsible
for credential revocation, storage, process I/O and closing retained documents.

## Mutable resources

`LocalFiles(root)` implements rooted local file operations. Specialized providers
may override physical mapping, listing, and stream reads/writes. All provider paths
are relative identifiers; do not open `root / path` as ordinary files for a virtual
provider. Providers expose `storage_id` (physical root) and `storage_namespace`
(opaque representation identity). Equal physical roots with unequal namespaces
must not take the direct-rename shortcut. Overlapping roots are rejected for
cross-provider transfers. Links, special files and hard-linked files are rejected.

The complete operation entry points are `move_resource`, `delete_resource` and
`save_resource_bytes`. UI/domain callers should use these rather than composing
copy/delete or encode/publish themselves. Provider hooks (`entry`, `create_file`,
`mkdir`, `rename`, `remove_empty`, `replace_created`) are backend mechanisms;
`entry` returns the listing fields plus an equality-comparable `revision` token.
Directory tokens identify the directory independently of child updates; inventory
comparison separately checks membership and all file revisions. `open` returns the
logical byte stream; `create_file` writes its logical input in the backend format.

Moves within an identical storage namespace use atomic no-replace rename.
Cross-provider moves stage a tree, compare SHA-256 of logical file contents, verify
source membership/revisions, publish without replacing an existing destination,
and only then remove the source. Empty folders are included. Save As uses the same
verified staging discipline with `expected_revision=None` (create only); ordinary
saves supply a revision. Temporary output belongs to the destination provider and
must use its representation. None of these operations requires a plaintext temp
file. Publication uses exclusive rename on Windows, Linux/Android and macOS/iOS;
unavailable platform primitives fail closed.

`mutation_lock` serializes in-process mutations and can wrap document saves using
`serialize_mutation`. It is not a cross-process writer lock. Directory-wide deletion
is not atomic; cancellation/error can leave remaining entries. A move failure after
publication leaves the verified destination and any unremoved source. No rollback
removes that destination. A process crash may leave an unpublished staging item;
there is no durable transaction journal or promise of whole-tree rollback.

Traversal rejects roots, parent components and unsafe names, and caps operations at
10,000 entries/100 levels. Cancellation is cooperative. ResourceBrowser exposes
create-folder, rename and confirmed deletion for mutable providers; host-specific
transfer pickers call `mutate(work)` to retain its worker/shutdown contract. The
library contains no encryption, credential or remote-service knowledge.

## Module ownership and explicit capabilities

Import contracts, `ResourceCapabilities` and path validation from
`runtime.resources.provider`, `LocalFiles` from `runtime.resources.local`, and complete
mutations from `runtime.resources.mutations`. `WritableDirectoryProvider` describes
revision-bearing entries, streams and mutation hooks. A provider declares immutable
`capabilities` (`create`, `rename`, `delete`, `replace`); an undeclared provider is
read-only. The browser checks these declarations independently for each action.
Inherited methods alone do not grant UI capabilities. Mutation entry points check
the needed capabilities before changing storage.

`persistence.publication` owns `mutation_lock`, `serialize_mutation`,
`rename_exclusive` and `save_transaction`. The transaction takes keyword callbacks
`stage`, `verify`, `validate`, `publish`, `cleanup`, and `cancelled`. It validates
before staging and again after verification, checks cancellation before publication,
and runs owned-stage cleanup on success and failure. `verify` may return the updated
document. The stage callback must allocate exclusively and track ownership even if
writing fails; cleanup must never remove an unrelated collision. Publication must
be atomic. A late cancellation does not turn a completed publication into failure.
Ordinary `atomic_write_bytes` uses this same transaction, including read-back
verification. Platform no-replace rename is shared with rooted provider operations.

`runtime.operations.MutationIncomplete` carries a `MutationResult` when an operation
changed storage but did not finish. `destination_published` identifies a verified
published destination. `source_state` is `unchanged`, `removed`, `partial`, or
`unknown`; `removed_paths` contains confirmed removals. `move_resource` and
`delete_resource` return results on completion. An error before publication may
remain its original exception. Hosts must retain the published destination and
refresh before retrying incomplete cleanup; they must not replay the whole move.
Cleanup failures in a save transaction also carry publication state. This is
in-process evidence, not a crash-recovery journal.

## Editor save integration

Storage adapters use `viewer.capture_save()` to capture encoded draft bytes,
`begin_save()` to reserve an asynchronous save, and
`complete_save(destination, data, error=None)` to finish it. Call these on the GUI
thread. A failed save keeps the draft and current location; successful completion
retargets the editor and clears dirty state. Hosts disable editing while the worker
runs and retain provider lifetimes through completion. No private editor fields
need to be accessed by storage adapters.

`persistence.text.TextSession` owns an in-memory text baseline, encoding/newlines,
resource key and opaque revision. `modified(draft)` and `encode(draft)` compare and
encode a host-owned draft; `accept(name, bytes, key=..., revision=...)` updates the
baseline only after a successful save. It never reads storage or persists recovery
state. Hosts retain their own archive readers, size limits and UI policy.

## Complete folder actions and raw-path boundaries

UI callers use `create_resource_folder` and `rename_resource` from
`runtime.resources.mutations`, alongside save/move/delete. These check capabilities
and cancellation before invoking backend primitives; controllers should not call
`mkdir` or `rename` directly.

A host can register a provider-owned physical root with
`filesystem.local_access.protect_local_root(owner, root, message)`. Ordinary atomic
writes, text/Markdown reads, rooted local providers, clipboard transfers, removal,
bulk rename and inline browser rename consult this boundary. Recursive raw
operations also reject ancestors containing a protected root, and checks resolve
symlink aliases. The owning virtual backend continues to map and publish through
its explicit backend operations. `provider_record_access(path)` grants one exact
internal record destination on the current thread, scoped to its context; it is
not a file-picker override or a general subtree exemption.

This is application routing protection, not an OS sandbox. Arbitrary third-party
filesystem calls are outside this contract. Hosts register roots at startup and
when opening or creating provider storage; registrations remain active when the
provider locks or closes. Unregister only when ownership actually ends.


## Shared Open / Save As selection

`runtime.resources.selection.ResourceSelection(provider, mode, extensions)` is the
widget-independent picker model. `list` filters/sorts directories and file types;
`resolve(directory, name)` validates relative paths, open targets, parent folders,
capabilities and destination collisions. `save` and `destination` are create-only;
mutation-time revalidation remains mandatory. Unavailable ordinary local entries
are omitted only in picker listings, never in recursive mutation inventories.

`ResourceChoice(provider, path, release)` transfers an owned provider lease;
`close()` is idempotent. The Qt `ui.resources.picker.ResourcePicker` reuses
`ResourceBrowser` with a read-only selection model and host-supplied location
factories. Closing waits for worker cancellation before releasing storage.
`ResourceTaskDialog` and `resource_tasks_pending` let hosts veto shutdown while
resource jobs retire. Mobile hosts can render the same model with native widgets.

`ResourceTextSession` reads bounded text with revision checks, preserves encoding
and line endings, and saves through verified resource transactions. Save returns
a new baseline only after reopening unchanged; reopening failure after publication
raises `MutationIncomplete`. `ui.resources.editor.ResourceTextWindow` is an optional
session-only plain editor; hosts supply Open/Save As selection and window routing.
It creates no recovery or recent-file records. Hosts remain responsible for
removing existing ordinary recovery drafts before a private handoff. Platform
publication dispatch stays in `persistence.publication`, using `get_os()`.


Rooted local providers expose `transfer_location(path, directory=False)` for
physical overlap validation, including providers which encode names. When two
storage roots overlap, shared moves compare these selected item locations rather
than rejecting the whole drive. Providers without this mapping retain the
conservative root-overlap rejection. This never bypasses local protected-root
checks or permits moving an item into itself or its descendants.


`runtime.resources.mutations.save_resource_and_reopen(provider, path, data,
reopen=callback, expected_revision=None, cancelled=...)` combines verified
publication with a host-owned reader preparation callback. Publication failures
propagate without invoking the callback. After publication, the callback must
reopen the destination and validate that its contents still match the saved data.
Callback failures raise `MutationIncomplete` with `destination_published=True`;
the published file is preserved. Late save cancellation does not skip reopening.
The host retains its old draft until both this call and UI replacement succeed.
`ResourceTextSession.publish` uses this operation and checks bytes itself.
The helper has no knowledge of encryption, credentials, formats or widgets.


## Shared item presentation

Provider snapshots carrying a non-null `BrowseRole.Revision` retain unchanged
thumbnail icons across listing updates. Removed or changed entries invalidate
their icons, and in-flight results from older snapshots are discarded. Providers
must change the revision when thumbnail content changes; entries without a revision
are conservatively invalidated. Source byte/range caches remain adapter-owned.

`runtime.browsing` provides the UI-independent `BrowseEntry`, `BrowseColumn` and
`BrowseTree`. Entry identities are opaque hashable values (except reserved `None`),
not filesystem paths. Entries have a label, container flag, custom properties,
optional source revision, opaque payload and optional thumbnail/badge callbacks.
Columns select properties by key; byte columns format numbers for display while
sorting their underlying values. Containers may represent directories, archive
members, remote groups or categories in a JSON dataset. `BrowseTree` validates
identity uniqueness, ancestry and snapshot size before publication. A changed
container revision removes its cached descendants. `updated_children` prepares a
validated copy for native UI adapters to publish with appropriate notifications.
No Qt, Toga, filesystem enumeration or persistent cache is imported by that module.

`ui.file_browser.entry_model.EntryModel` projects that tree into a Qt item model.
`children_requested(identity)` asks the host to supply a missing listing; it does
not perform I/O. The host retrieves children on its worker and calls
`set_children` on the GUI thread. `BrowseRole` exposes identity, container status,
typed sort values, revision, thumbnail callback, badge and editable suffix.
`EntryModel` supports custom columns and optional filtering. Its bounded snapshot
cache defaults to 10,000 total entries; pagination and source-specific eviction
are not implemented in this first phase. Failed snapshots leave existing data intact.

`ui.file_browser.views.BrowserViews` owns the shared list/tile/column presentation,
selection transfer, responsive tile sizes, column context and RAM thumbnail queue.
`FileViews` adds only local storage-chart integration. The existing
`BrowserFileSystemModel` supplies these roles and identity/ancestry methods while
retaining Qt filesystem watching, file objects, format registration and local
rename. Its local index/search/preview/action host is unchanged. `ProviderEntryModel`
adapts the existing directory contract without inspecting virtual paths on disk;
`ResourceBrowser` owns its cancellable listing queue and provider mutations.
The picker uses these same views and keeps storage selection at the top.

`ResourceBrowser(..., details=loader, preview=True)` uses the established preview
widgets and `DetailsPanel`. Generic file fields appear immediately; the optional
worker callback `loader(row, cancelled)` returns `(tab_title, BrowserDetails)`
pairs. Hosts own domain metadata and provider cancellation scopes. Selection
changes cancel obsolete work and discard stale results. `preview=False` omits
the panel; Open/Save As pickers select this setting. List/tile views place the
panel in the right splitter and column view uses its final preview column.
Preview workers count toward `busy` and cooperative `stop()`.

The shared thumbnail queue runs at most two visible-item callbacks concurrently.
Off-screen requests are skipped, stale revisions are discarded and `stop()` waits
for all workers before the owner can release its provider. Decoders may request
scaled image sizes to avoid unnecessary full-resolution JPEG work.

Thumbnail callbacks receive `(physical_pixel_size, cancelled)` and return encoded
image bytes. Provider browser callbacks additionally receive the relative path:
`thumbnail(path, size, cancelled)`. They must use the provider rather than opening
virtual identifiers as files. The browser scopes backend work through an optional
provider `operation(cancelled)` context. Default image previews read at most 16 MiB
and reject images above 16 million pixels. Hosts may supply domain cover callbacks.
Decoded pixmaps are made on the GUI thread, cached only in RAM (up to 128 entries)
and invalidated on snapshot changes and requested resolution changes. Old worker
results cannot repopulate a reset/closed view. Close and storage switching retain
the provider until listing and thumbnail workers retire; picker validation can run
while a thumbnail finishes, but acceptance waits for retirement. Unknown or locked
covers fall back to generic icons without prompting or writing cache files.

`BrowserKeyboard(browser, execute=callback)` reuses the regular platform shortcuts
for a host that supplies item actions without indexed search or filesystem commands.
Provider browsing retains create-folder/rename/delete and host-supplied Move actions;
selection payloads remain provider rows. Compatibility row accessors on ProviderTree
serve existing `topLevelItemCount`, `topLevelItem` and `selectedItems` consumers;
new integrations use `ResourceBrowser.selected_rows()` across every view.

`ui.native_browser.NativeBrowser` provides Toga list/tile presentation over the
same portable BrowseTree and provider/mutation contracts. It requires Toga only
when imported, and does not import Qt. Archive, remote and JSON sources can build
on the generic entries; production adapters and a universal browser host remain
future work.

A minimal non-filesystem model:

```python
from commonUtils.runtime.browsing import BrowseEntry, BrowseColumn
from commonUtils.ui.file_browser.entry_model import EntryModel

model = EntryModel(BrowseEntry(('taxonomy', 0), 'Animal kingdom', True),
                   [BrowseColumn('name', 'Species'),
                    BrowseColumn('habitat', 'Habitat')])
model.set_children(('taxonomy', 0),
                   [BrowseEntry(42, 'Lion', properties={'habitat': 'Savanna'})])
```


### Native list and tile presentation

The [continuous native browser](native_browser/README.md#continuous-mobile-browsing)
uses this same model and callbacks with recycled rows and viewport-limited tiles.
Import it explicitly as `ui.native_browser.recycled.RecycledBrowser`; the base
class below retains its existing paginated presentation.

`NativeBrowser(selected=callback, thumbnail=loader, details=loader, preview=True)`
creates a native Toga component. Hosts publish prepared BrowseTree snapshots via
`set_tree(tree)` or provider rows through `set_entries(provider, directory, rows)`.
`runtime.browsing.provider_entries` is the shared provider-row conversion used by
both native and Qt models. Arbitrary identities/properties remain available through
`set_tree`, without treating JSON/archive identities as disk paths.

List and Tiles retain selection and page through 24/16 entries respectively by
default. Hosts can override the `page_size` property to bound a larger scrolling
listing. Generic folders use a text glyph with no image load. Image widgets are
created only for files with a thumbnail loader or cached thumbnail.
Thumbnail workers receive `(row_payload, pixel_size, cancelled)` and return encoded
image bytes; rich details receive `(row_payload, cancelled)` and return label/value
pairs. Generic Name/Type/Size/Modified fields appear immediately below entries.
`preview=False` omits details for a picker. Hosts own navigation, activation, source
adapters, storage selection and mutations. No I/O occurs during painting.

At most two thumbnail workers run concurrently. The encoded thumbnail LRU is
limited to 64 entries and 8 MiB. Snapshot changes invalidate unknown/changed
revisions and stale results. `stop()` signals cancellation and clears all displayed
entries, details and covers. Owners await `close()` to retain worker dependencies
until work retires before releasing them. They may publish a fresh snapshot after
stopping. Worker callbacks must honor cancellation and validate their source lease.

`RangeReader(..., validate=callback)` checks its source lease before every read or
seek, including cache hits. This allows credential/revision revocation without
returning previously cached plaintext after locking; `close()` clears range blocks.


### Native navigation and recursive queries

`NativeBrowser(open_folder=callback, navigate=callback, ...)` optionally delegates
folder taps and Back to a host. Folder callbacks receive the selected row payload;
navigation callbacks receive an opaque location supplied with
`set_entries(..., location=...)`. Hosts publish a new snapshot only after a successful
load and return false on failure, preserving the previous displayed snapshot.
Back restores its prior history on failed loads. `runtime.browsing.BrowseHistory`
retains at most 100 locations; identical refreshes do not add another visit.
No source resolution, credentials or I/O belong to this history model.

`search.names` owns the keyword/phrase rules also used by SQLite snapshots:
bare terms are Unicode-casefolded substrings joined with AND; double-quoted phrases
preserve adjacency/order with equivalent whitespace, underscore and hyphen separators.
`runtime.browsing.query_entries` filters supplied labels with these rules and
sorts natural names, numeric sizes or modified values in either direction while
retaining containers first. `search.providers.search_resources` walks
provider listings breadth-first, validates child scope and produces relative labels
for nested matches. Desktop ResourceBrowser and NativeBrowser debounce searches
for 400 ms after the last edit and run this scan on cancellable workers.
The default scan visits the full subtree; callers can explicitly set max_entries.
An optional `progress(SearchResult)` callback runs on the scanning thread with detached,
incomplete snapshots. It publishes the first match immediately, then throttles
updates to at most four per second. Callers marshal these snapshots to their UI loop;
the returned result carries final completeness and errors. NativeBrowser publishes
these matches while scanning continues and discards obsolete query results.
An optional provider search_entries(directory, cancelled=...) iterator supplies a
recursive listing directly; its rows must stay strictly beneath the requested
directory. Partial or failed listings must not be presented as complete.
Partial results report limits or unreadable folders; credentials failures abort.
The default search retains no durable index or file content. Hosts can pass
`NativeBrowser(resource_search=callback)` to select a different backend. It runs
on the search worker with `(provider, directory, query, cancelled=..., progress=...)`
and returns `SearchResult`; progress has the same detached-result contract. The
host owns database policy, source eligibility and reconciliation. No UI access
belongs in this callback. Final results replace earlier snapshots even when the
number of matches stays the same. Sorting reprojects the current
snapshot without rescanning; closing search restores the original folder tree. Selection is cleared when filtered out
and `selected(None)` notifies the host. Search resets on location changes. Closing
clears history, query and private display data. Hosts retain navigation, selected
source ownership, failures and domain-specific file activation.

### Local streamed archive sources

`runtime.resources.archives.LocalArchiveSource(path, max_read=..., max_members=...)`
implements a revision-checked, seekable local archive source without an overall
file-size cap or extraction. `open_archive` yields a ZIP facade with bounded `read`
for explicitly requested members; `open(member)` exposes a stream for host-owned
chunked processing. Header count, safe names and unencrypted/regular-file checks
precede use. Opening/reading rejects changed source revisions. It requires neither
Qt, native mobile bridges, image libraries nor password ZIP dependencies. Format
policy and image decode limits remain host-owned.
