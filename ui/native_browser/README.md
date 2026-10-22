# Native item browser

Toga list/tile presentation for portable BrowseTree snapshots and rooted provider
rows. See the [shared contract](../resource-providers.md#native-list-and-tile-presentation)
for callbacks, cache bounds and cooperative shutdown. Import this module directly;
Toga is optional for consumers that only use the portable model or Qt views.

## Continuous mobile browsing

Import `RecycledBrowser` and `BrowserPresentation` from
`commonUtils.ui.native_browser.recycled` for a continuous native list and
viewport-limited two-column tiles. The existing `NativeBrowser` retains its
paginated presentation. Both consume the same provider snapshots and search model.

```python
from commonUtils.ui.native_browser.recycled import RecycledBrowser

# Construct inside a Toga App with its owning event loop.
browser = RecycledBrowser(open_file=lambda row: open_document(row), preview=False)
browser.set_entries(provider, '', rows)
content = browser.scroll_container()
```

Mount `content` directly in the available viewport; do not wrap the native list
in another scroll container. `vertical_position` and `max_vertical_position`
delegate to the active list/tile viewport. Retain the browser until `await
browser.close()` finishes. `stop()` clears rows, thumbnails, menus and tile tasks;
an old row cannot activate a replaced snapshot.

`open_file(payload)` bypasses details loading for direct document opening.
`item_actions(payload)` runs after guarded contextual selection.
`inline_details=False` leaves information-panel hosting to the caller; otherwise
the panel is mounted below the viewport when `preview=True`. Folder opening,
navigation, selection, thumbnail and details callbacks follow the base browser
contract. Callbacks may be asynchronous. Source leases, credentials, visibility
policy, action approval and document lifetime remain with the host.

Supply `presentation=BrowserPresentation()` or a subclass to customize command
icons/styles, `file_icon(folder)`, `entry_icon(folder)`, tile button styling,
selection highlighting and keyboard binding. `list_factory` accepts the same
keyword arguments as [RecycledList](../native/README.md#recycled-lists); a host
factory can inject its `ListAppearance` and register theme refreshes. Hosts that
compose native row menus can assign an async `native_list.menu_provider(row)`
returning UIKit menu elements; it must reject revoked or obsolete actions.

Lists publish lightweight records for the complete result set; native cells
recycle. Decoded thumbnails and rows holding thumbnails each retain at most 64
images, with at most 24 pending visible-row requests. The inherited worker and
encoded-cache limits still apply. Tiles retain at most 40 two-item rows and
cancel thumbnail work when cards leave the window. Snapshot/query epochs reject
late results. These limits bound widgets/images, not the complete row inventory.

## Shared work and thumbnail lifetime

`lifecycle.BrowserLifecycle` owns thumbnail epochs,
cooperative cancellation, retained async tasks and encoded/decoded caches.
`paginated.PaginatedRenderer` builds bounded widget pages; `RecycledBrowser`
provides native recycled rows and bounded tiles. Rendering policy stays separate
while both use the same worker and revision lifetime.

Thumbnail cache keys are `(entry.identity, entry.revision)`. At most two loaders
run concurrently. Encoded data is bounded to 64 entries and 8 MiB; recycled
native decoded images are bounded to 64 entries. Invalidating a snapshot signals
its cancellation event and advances the epoch, so late results cannot publish.
Unavailable covers do not prevent selecting the resource.

When a tile leaves the viewport, its cancellation event is signalled while its
storage-read task stays retained until the loader returns. Cancelling an async
awaiter cannot stop a blocking worker thread; retaining the task also keeps its
concurrency slot occupied until the read retires. Queued obsolete requests skip
loading when they acquire a slot.

`stop()` invalidates work and clears caches immediately; `await close()` waits for
retained tasks, including cooperative worker completion. Close explicitly drains
completed tasks even before their queued retirement callbacks run. Do not release
storage leases merely because rows disappeared. For a memory trim,
`work.prune(set())` clears both cache tiers without changing selection. Hosts must
also release their own displayed image references when appropriate. Stop/close
remain the retirement path.
