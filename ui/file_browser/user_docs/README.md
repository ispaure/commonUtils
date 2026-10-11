# Using the File Browser

The shared File Browser lets you navigate folders, inspect files, search saved
filenames and explore folder sizes. Your application may add file-specific actions,
readers or restrictions. Those additions are described by the application.

## Browse and inspect

Open folders with a double-click. Breadcrumbs jump to a parent location; Back and
Forward revisit navigation history. Some browsers are restricted to an initial
folder, while others allow broader filesystem navigation. On Windows an unrestricted
browser can expose drive/network locations through its root breadcrumb.

Choose tiles, a list or columns according to your task. The Size control changes
icon/tile presentation. Preview shows details for the selection, or folder properties
when nothing is selected. Hide it to give the file list more room and avoid automatic
selection-detail loading. Column view uses its own final details column; size maps
use a ranked entry list instead. Optional previews depend on file type and installed
application features; opening a file may use an application-supplied reader.

Keyboard navigation follows the platform: macOS uses Command-Up for the parent,
Command-Down/Command-O to open, and Return to rename. Windows/Linux use Enter to
open, F2 to rename and Alt-Up for the parent; Windows also accepts Backspace.
Text fields and filename editors retain their own text-editing keys.

## Find files by name

Press Ctrl/Cmd+F or choose Search. Searches use the saved index beneath the current
folder, not document contents. All bare words must occur, in any order. A quoted
phrase keeps word order and treats spaces, underscores and hyphens as equivalent
separators. Matching ignores case; wildcard characters are literal.

For example, `annual report` matches a name containing both words, while
`"annual report"` also matches `annual-report` but not `report annual`.
Results appear in pages of 500; sorting applies to the entire match set. Opening a
result folder keeps the query and narrows its scope. **Show in browser** exits search
and locates the result. Escape or the search close control returns to normal browsing.

An incomplete index means incomplete results. The ordinary file list can show a
new file before search knows about it. Use **Refresh index** to check the current
subtree, and **Index details…** to inspect errors or unfinished work. Search itself
does not start a separate scan.

## Understand folder sizes

Treemap and Radial views use saved logical file sizes. Larger areas mean more bytes;
the companion list ranks entries by size. Double-click a folder to explore it.
The radial centre can return to the parent within the browser's navigation boundary.

Radial shows at most four levels and 3,000 entries; treemap immediate-child reads
are also bounded to 3,000. Gaps can represent omitted entries, zero-byte folders or
incomplete indexing. Root totals can include entries not individually drawn.
Percentages refer to the current root. Sizes are logical bytes, so hard links,
clones and sparse files can make them differ from physical disk consumption.

Indexing stores paths and metadata in a local cache, not file contents. It can use
substantial disk space for large trees. Results stay usable while updates run.
Initial/partial work saves completed folders; interrupted folders need another
pass. Failed branches remain partial until an explicit retry. There is no visible
Pause/Resume control in the current browser.

After initial work, filesystem notifications and explicit refresh drive updates;
there is no periodic full-tree validation. Changes in an unwatched folder can stay
cached. **Refresh index** validates the current subtree; it is different from simply
redrawing a view. The control is available when indexing is idle. **Index details…**
shows up to 500 diagnostic rows, while counts cover the whole current subtree.

Network locations deliberately disable indexing, size maps, indexed search and
automatic cover/metadata extraction. Normal browsing and explicit opening remain
available. A missing search or size control on a network drive is expected.

## Work in multiple tabs or windows

When the application hosts the browser in the shared docking workspace, tabs browse
independently. Drag horizontally within the tab bar to reorder. Drag a tab out to
detach its pane; drop in the centre of a compatible group to tabify, or use a side
drop zone to split. Escape cancels a drag. Detached-window controls depend on the
host's workspace policy. Some hosts keep the final attached browser tab open.

Tabs can share index work while showing different folders. Closing one tab need
not stop another tab's scan. A closing tab may disappear while its background work
finishes; the application retains it until shutdown is safe. Feature-specific
unsaved changes can veto closing.

## Copy, rename and remove

Use the selection's context menu for available file operations. Application-added
actions may accept only some types in a mixed selection. Recheck the selection and
destination before confirming an operation; there is no universal undo for disk changes.

**Move to Trash / Recycle Bin…** asks for confirmation, with selected names and full
paths in Details. Selecting a folder includes its contents. A failed trash operation
leaves affected items in place and offers error details. Permanent deletion requires
choosing **Review permanent deletion…** and confirming a second warning; it never
happens automatically as a fallback. Permanent deletion can partially complete and
cannot be undone through the browser. Links are removed without deleting their target.
Delete inside a text field edits text rather than removing a file.

## Settings and their effects

Your application decides how to expose the shared INI or an application-specific
index settings file. Save changes explicitly. These are shared behavior settings,
not a guarantee that every host provides a settings dialog.

| Setting | Effect and tradeoff |
| --- | --- |
| `[FileBrowser] preview_enabled` | True starts new tabs with previews; false avoids automatic detail loading until enabled. Existing tabs can override with Preview. |
| `[Storage] radial_animations_bool` | True animates folder zooms; false changes folders immediately. It does not alter indexed sizes. |
| `[FileIndex] scan_on_open` | True permits discovery when saved data is missing; false favors saved results until explicit refresh. |
| `recursive_on_open` | True permits initial descendant discovery; false limits initial discovery, reducing work but leaving deeper results unavailable until indexed. |
| `refresh_cached_on_startup` | True permits checking saved data on opening; false prefers cached data. Combined with scan_on_open, a missing cache can still trigger discovery. |
| `refresh_on_revisit` | True checks a reopened current location again; false avoids that extra revisit check. Notifications and explicit refresh are separate. |
| `watch_changes` | True responds to watched filesystem changes; false reduces automatic updates but permits stale saved sizes. It does not disable ordinary live browsing. |
| `background_priority` | True starts index workers at lower thread priority; false uses inherited priority. Both still perform filesystem work. |

The last six keys are in `[FileIndex]`. Without a custom settings path their fallback
values are true except `refresh_on_revisit`. With an application-supplied index path,
`recursive_on_open` and `refresh_cached_on_startup` additionally default to false.
Applications can override these defaults. Turning off automatic work does not make
saved metadata current; use explicit refresh when completeness matters.

## Troubleshooting

- **Files appear but search/sizes are missing:** allow discovery to finish, inspect
  partial-state details, check index policy and whether the path is a network location.
- **Sizes look old:** refresh the subtree. Reading a cached view alone is not validation.
- **A preview is absent:** enable Preview in tiles/list; the type may not supply one,
  or the file may be unreadable. Network paths suppress automatic rich previews.
- **Closing takes time:** a filesystem operation may need to return before cancellation
  is observed. Another tab can continue shared work after this one closes.
- **Removal failed:** read Details, check permissions/trash support and retain files
  unless permanent removal is explicitly intended.

[Developer integration](../README.md) · [All shared guides](../../../README.md#shared-component-user-guides)
