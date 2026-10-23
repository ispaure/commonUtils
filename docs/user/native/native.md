# Native controls and document access

An application using these optional components can provide native destination
tabs or a wider-screen rail/sidebar, with separate Back history in each destination.
The application decides destination names, available screens and close prompts.
On Android phones, opening the keyboard keeps the destination bar at its normal
height above the keyboard so the active screen can use the remaining space.

For images, pinch to zoom and drag to pan. At fit size, horizontal swipes ask the
application to change images; some readers use up/down swipes instead. Tap asks the application to show or hide controls.
Fit returns to the centered image. The application owns image order, reading
direction and whether paging is available.
Readers can reserve horizontal swipes, including screen-edge swipes, for paging.
In those readers, use the application's Back button to leave the screen. Dragging
a zoomed image continues to pan; fit the image before swiping to another page.

When the application enables the magnifying bubble, hold the image briefly,
then drag to move the bubble. It enlarges the image beneath the bubble’s center,
above your finger, and is larger on tablets. Near an edge, keep dragging toward
the border to inspect the outermost pixels after the bubble stops moving. Release
to dismiss it. Keep holding the image and tap −/+ just outside the bubble’s bottom
left/right corners with another finger to adjust it from 150% to 250% in 20% steps.
The compact buttons do not display a zoom percentage. The application decides whether to remember this value.
A second finger away from the buttons still cancels the bubble for ordinary image pinch zoom.

Applications can also use system document pickers. Opening a document grants
scoped access while it is being imported; the application chooses where to keep
its copy. Export asks you to choose a destination. Cancelling leaves the original
source untouched; the selected document provider controls how exported data is saved.

Native action menus show commands supplied by the application. In text editors,
Find supports previous/next matches, wrapping and optional case matching. Replace
uses literal text, including backslashes, and Replace all updates every match.
The application controls whether editing and saving are available.

[Embedding and packaging](../../reference/ui/native/native.md)

## Documentation

A native app can show an offline Markdown wiki. The hamburger button shows folders, pages and search in narrow windows; tap it
again to return to the article. Wider windows keep the list beside the article. Use the chevron to
expand or collapse folders, and tap the title separately to open its page. File names & titles searches
navigation labels and names; Page text searches Markdown source. Clear the query
to show the full tree. The search-mode selector appears only while a library
query is entered. Matching text is highlighted when you open a result; a match
in a filename alone may have no matching passage in the rendered page.

Use the magnifying glass for **Find in this page**. Its controls sit above the
article, separate from library search, with a current/total count and Previous/Next
arrows that wrap. Search is literal and case-insensitive, including text across
inline formatting. **Done** removes page marks while keeping library marks until
the library query is cleared. At most 5,000 matches per scope are highlighted;
a count ending in `+` indicates that limit. Search changes no source text, links
or speech highlights. The viewer is read-only; the host app owns editing.

The top bar provides Back, Forward and Up. Back/Forward revisit pages you have
opened. Up opens the containing folder's same-named Markdown page; from that
folder page it opens the parent folder's page. At the documentation root,
README.md or index.md can serve as the folder page. Up is disabled when that
folder has no page or you are already at the root page.

When the root folder has a same-named page, it is the single top entry and all
other documentation is nested beneath it. Expanded child pages and folders are indented beneath their parent; titles at
the same depth line up. Markdown articles support tables (swipe sideways when
wide), nested lists, quotes, emphasis, code and local heading links. Raw HTML is
shown as text; images show alternative text and external links remain inert.

A folder opens its same-named page (for example, `banana/banana.md`). Guides
begin with a title heading, which also names them in the tree. A link to another
documentation wiki changes the sidebar to that guide's files. Back and Forward
return to the corresponding guide and tree. Search clears on a scope change.

## Source editing

An app can use the native source editor for text, Markdown and configuration/code
files. It shows logical line numbers beside monospace text and syntax colours for
the chosen language. Wrapped continuations keep their original line number.
The native keyboard, selection and undo stay available. Large files can remain
editable with colours paused; the app controls files, saving and any live preview.

## Password visibility

Password and token controls start hidden. Use the eye button to show or hide the
current value. Clearing the field hides it again. The application decides when
credentials are submitted, retained or cleared.

## Images supplied by an app

Apps can enable inline PNG, JPEG and WebP images in native Markdown views.
The app decides which image files are accessible and supplies their bytes;
the renderer embeds them without fetching network resources. Missing or
unsupported images show alternative text. Views without this opt-in, including
the documentation wiki, continue to show image alternative text.

## Text and reader controls

Where enabled by the host, pinch text to preview a new size and release to save
it. Page changes can use a short slide; system reduced-motion settings and the
host's animation preferences determine whether it appears. Reader sliders keep
full touch areas around their slim visual tracks. The host controls page order,
reading direction and which settings persist.

Native icon controls keep their full button hit target and accessible action name.
Leading glyphs remain part of the same control as its title. Applications supply
the artwork, labels and colors; rendering preserves callbacks and enabled state.

## Forms

Form labels fit the available pane, including long unbroken identifiers and
changing status messages. Disclosure buttons retain their full accessible hit
area. Collapsing advanced fields hides them while preserving entered values.
