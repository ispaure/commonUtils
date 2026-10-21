# Browse native items

Choose **List** for compact rows or **Tiles** for larger cover images. **Previous**
and **Next** show the next page of items. Select an entry to see file information
below the list, including available format metadata. Hosts may omit this information
for an Open/Save picker and supply their own folder and Open buttons.
The host application determines how many items fit on one scrolling page.

Hosts using the continuous browser show all matching rows in one scrolling list;
scroll to reach later items instead of using Previous/Next. Tiles load as they
enter the visible area. A row's contextual button selects it for actions; a
normal tap opens it when the host supplies an Open action.

Covers load in the background. Missing or locked covers leave names selectable;
view changes and closing stop obsolete work. Thumbnails stay in memory.


Tap a folder to enter it when the host enables navigation. **Back** returns to the
previous successfully loaded location, including a previous storage selection.
The bounded history lasts only for this browser session and is cleared on closing.

**Search** opens a full-width field to search this folder and its subfolders.
Folder listings load in the background without reading file contents. Matches
appear while the scan continues; the status reports ongoing searches, partial
results and failures. Searches cover the subtree unless the host sets a scan
limit. Closing search restores the folder listing. Sorting offers natural names, sizes or modified times in either direction;
folders stay before files. Search resets when navigating elsewhere. Hidden selected
items are deselected so actions cannot target an item excluded by the filter.
