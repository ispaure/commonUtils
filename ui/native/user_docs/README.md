# Native controls and document access

An application using these optional components can provide native destination
tabs or a wider-screen rail/sidebar, with separate Back history in each destination.
The application decides destination names, available screens and close prompts.

For images, pinch to zoom and drag to pan. At fit size, horizontal swipes ask the
application to change images. Tap asks the application to show or hide controls.
Fit returns to the centered image. The application owns image order, reading
direction and whether paging is available.
Readers can reserve horizontal swipes, including screen-edge swipes, for paging.
In those readers, use the application's Back button to leave the screen. Dragging
a zoomed image continues to pan; fit the image before swiping to another page.

When the application enables the magnifying bubble, hold the image briefly,
then drag to move the bubble. It enlarges the image beneath the bubble’s center,
above your finger, and is larger on tablets. Near an edge, keep dragging toward
the border to inspect the outermost pixels after the bubble stops moving. Release
to dismiss it; a second finger cancels it for pinch zoom.

Applications can also use system document pickers. Opening a document grants
scoped access while it is being imported; the application chooses where to keep
its copy. Export asks you to choose a destination. Cancelling leaves the original
source untouched; the selected document provider controls how exported data is saved.

Native action menus show commands supplied by the application. In text editors,
Find supports previous/next matches, wrapping and optional case matching. Replace
uses literal text, including backslashes, and Replace all updates every match.
The application controls whether editing and saving are available.

[Embedding and packaging](../README.md)

## Documentation

A native app can show an offline Markdown wiki. The hamburger button shows folders, pages and search in narrow windows; tap it
again to return to the article. Wider windows keep the list beside the article. Use + or − to
expand folders, and tap the title to open its page. File names & titles searches
navigation labels and names; Page text searches Markdown source. Clear the query
to show the full tree. The viewer is read-only; the host app owns editing.

The top bar provides Back, Forward and Up. Back/Forward revisit pages you have
opened. Up opens the containing folder's same-named Markdown page; from that
folder page it opens the parent folder's page. At the documentation root,
README.md or index.md can serve as the folder page. Up is disabled when that
folder has no page or you are already at the root page.

Expanded child pages and folders are indented beneath their parent; titles at
the same depth line up. Markdown articles support tables (swipe sideways when
wide), nested lists, quotes, emphasis, code and local heading links. Raw HTML is
shown as text; images show alternative text and external links remain inert.

A folder opens its same-named page (for example, `banana/banana.md`). Guides
begin with a title heading, which also names them in the tree. A link to another
documentation wiki changes the sidebar to that guide's files. Back and Forward
return to the corresponding guide and tree. Search clears on a scope change.
