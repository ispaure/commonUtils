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

Hidden files and folders use muted grey text in these views and cached search
results. Dot-prefixed names are muted on every desktop platform, along with
Windows entries marked Hidden and macOS entries carrying the native hidden flag.
They remain selectable and open normally when displayed.

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

Treemap and Radial default to **Size on disk (allocated space)**. The **Measure**
dropdown above the chart switches to **Size (file contents)**. Size on disk measures
the space allocated to files, including block rounding and sparse/compressed storage;
Size measures their content length. Larger areas mean more of the selected measure,
and the companion list ranks entries by that same measure. Both values are cached;
switching measures does not scan files again. Double-click a folder to explore it.
The radial centre can return to the parent within the browser's navigation boundary.

Radial shows at most four levels and 3,000 entries; treemap immediate-child reads
are also bounded to 3,000. Gaps can represent omitted entries, zero-byte folders or
incomplete indexing. Root totals can include entries not individually drawn.
Percentages refer to the current root and selected measure. Totals count files by
path, so hard links and clones may count shared storage more than once. Folder and
filesystem metadata are excluded. Unavailable allocations are excluded from the
allocated total and reported above the chart; they are never replaced with file
content size. Saved indexes created before allocation support retain their content
sizes, and collect allocations on the next metadata validation or Refresh index.

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

Applications that enable shared indexing across processes can also show work from
another running instance. Closing or pausing a view detaches it; queued work stays
available for another instance to finish. If every instance closes, the next launch
can resume saved checkpoints. This applies to indexing only. The application owns
whether this shared service is enabled.

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

The shared **File browser font** setting controls text inside the browser panel:
file/folder rows and headers, tile captions, folder columns, storage labels,
path/navigation controls, search and details text. Application navigation,
settings categories and menus use the interface font. Document readers and
editors use their reading/code font settings.

- **Files appear but search/sizes are missing:** allow discovery to finish, inspect
  partial-state details, check index policy and whether the path is a network location.
- **Sizes look old:** refresh the subtree. Reading a cached view alone is not validation.
- **A preview is absent:** enable Preview in tiles/list; the type may not supply one,
  or the file may be unreadable. Network paths suppress automatic rich previews.
- **Closing takes time:** a filesystem operation may need to return before cancellation
  is observed. Another tab can continue shared work after this one closes.
- **Removal failed:** read Details, check permissions/trash support and retain files
  unless permanent removal is explicitly intended.

[Developer integration](../../reference/ui/file_browser/file_browser.md) · [All shared guides](../../overview.md#shared-component-user-guides)

## Pick and drop links

Right-click one file or folder and choose **Pick Link Source**. In the destination
folder, right-click empty space (or the destination folder) and choose
**Drop Link As → Symbolic Link**. This creates a reference to the source without
copying its contents. The picked source is shared across browser views in the
same application session, remains available for further drops, and does not change
your Copy/Cut clipboard. **Cancel Link Creation** clears it.

For files, **Hard Link** is available on the same filesystem/volume: both names
refer to the same file, so editing through either name changes that file. For
local Windows folders, **Junction** is also available. Symbolic links support files
and folders; Windows may require Developer Mode or symbolic-link privileges.
Network folders should use symbolic links. Failures are reported without automatic
elevation. A missing source disables drop actions. Existing destination files are
never replaced: name collisions get ` - Link`, then a numbered suffix. Native
Windows link creation still requires validation on a Windows host.

Tile thumbnails can show a small status badge at their top-right when the host's
file type supplies one. Visible badges refresh as their status changes.

## Drag files and folders

Drag selected files or folders onto a folder, or onto a view's empty background,
to move them within Logistics. Hold Ctrl (Option on macOS) to copy instead. A
highlight marks the receiving folder or current-directory background. List, tile,
and folder-column views support drops. Files dragged in from another application
are copied; their originals remain in place. Local files can also be dragged out
to applications that accept file URLs.

Drops use the same progress, cancellation and collision handling as paste.
Existing destinations are not overwritten; collisions receive numbered copy names.
Moving a folder into itself or a descendant is refused. Drops do not replace or
clear the Copy/Cut clipboard. Web URLs are not accepted as filesystem items.


## Storage-aware Open and Save As

Hosts can use a compact, session-only resource browser as their Open/Save As
window. Select a storage location, navigate folders, and select or enter a name.
The host supplies available locations and unlock prompts. This picker shares
navigation with the resource browser but does not expose destructive context
menu actions. Save As requires an unused name and a valid existing parent folder.
Closing during a folder read or selection check cancels safely before releasing
storage. Neither navigation history nor decoded names are saved by this picker.


Applications can redirect managed folders into their own browser when you open,
expand or navigate into them. The regular browser then keeps its previous location
and does not display the managed folder's underlying files.

## Provider-backed folder browsing

Applications can also present a provider-backed browser. It uses the same compact navigation buttons and clickable folder breadcrumbs with a filterable Name/Date Modified/Size list (in that order), tile view and column navigation. The Size slider adjusts icons and tiles. Its optional Preview panel shows file information and host-supplied metadata on the right in list/tile view or in the final column. Modified dates use local time in the same readable format as local files, for example **Feb 11, 2026 at 6:45 PM**. Missing or invalid dates show **—**. Provider browsers omit storage maps. Open/Save As dialogs omit Preview and keep an application-supplied storage selector at the top. The dialog title begins with **🕵️ Private -** when its selected provider declares private storage. Session-only text editor titles also use that prefix and retain it after Save As. Provider thumbnails stay in memory; missing or locked covers use generic icons. Two visible thumbnails can load at once, and closing waits for both workers.
