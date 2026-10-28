# Reading and editing Markdown

The shared Markdown reader opens local `.md` and `.markdown` documents with headings,
links, images, tables and fenced code. It also supports local wiki-style links,
Obsidian-style callouts and a limited YAML properties editor. It is a document
reader/editor, not an Obsidian vault manager: there is no vault search, plugin system
or vault-wide property registry.

## Read and navigate

Ordinary file-browser activation opens preview. Hold Alt/Option while opening to
start editing, or use a host action explicitly labeled as an editor.

Use Contents to jump to headings and Back/Forward to return to earlier documents
and scroll positions. Following a Markdown link keeps the current Read/Edit mode
and Formatted/Source choice. Relative links resolve beside the current document. Wiki links
such as `[[Notes|My notes]]` target local documents; extensionless targets gain `.md`.
A similarly named document elsewhere in a vault is not automatically discovered.
Web/mail links open in the operating system's default application. Local non-Markdown
links and other URL schemes are not launched by this reader.

Native Markdown previews also recognize bare wiki links such as `[[Tech]]`,
including inside headings, when the host enables local links. The host chooses
how to find the destination. Code spans and image embeds keep their own meaning.

The default reading size is 10 reference points (about 13.3 logical pixels). Saved
reading-size preferences take precedence over this default. Inline
code and fenced code use that same reading size with a monospace family; changing
the code editor size does not resize code inside rendered Markdown. Wide windows
center a reading column of roughly 88 text characters; narrow windows wrap to fit.

Reading appearance adjusts text from 10–24 pt for the current window without changing
the file or editing font. Reading follows the host's light/dark palette. F11 toggles
fullscreen. Escape closes Contents/Find first, then leaves fullscreen. Missing or
unreadable linked documents show an error and retain the current page.

Callouts display as quote panels. A `+` callout starts expanded; a `-` callout starts
collapsed. Click its title to fold/unfold it. Folding never changes the file. Embedded
HTML is shown literally; this is not a full web-page renderer.

Fenced code is shown in a continuous monospace panel, preserving indentation and
blank lines. A language such as `vbnet` appears as a small label above the code.
Recognized languages receive syntax colors when Pygments is available; unknown
languages remain readable plain code. Both triple-backtick and longer fences work.
Language labels are presentation only and are not added to copied code or source.
Code blocks share the code editor's light/dark syntax accents; module paths and
function names keep the existing plain code color.

## Choose an editing mode

Some hosts open documents for reading only. Where editing is enabled, **Read** shows
the current rendered document, including unsaved edits, and **Edit** returns to the
editor. Standalone windows can also enable editing when opened with Alt held.

**Formatted** mode lets you edit rendered headings, emphasis, lists, links and tables.
Newly loaded formatted content starts with the caret and view at the beginning.
Supported Markdown markers become visible when the caret touches or is inside an
element, or a selection overlaps it. Hovering leaves the markers hidden. Click a
link label to navigate, including while editing; click its revealed syntax to edit
the destination, or Shift-click/drag to select text. Ctrl/Command-click also follows
links from their syntax. The Bold, Italic, Undo and Redo icon buttons match the mobile editor. Hover or
focus a button for its label and shortcut. The **Format** icon menu beside them contains
undo/redo, inline styles, headings, lists and quotes. **Format → Table** commands insert a table or add/remove rows and columns;
the first row is the header. Structural table changes are undoable.

**Source** exposes the Markdown text. Use it for exact syntax and unsupported
extensions. Actual formatted edits can normalize spacing, list/table/fence spelling
or lose unsupported constructs through Qt's Markdown conversion. Merely reading or
saving without edits preserves the original bytes. Callout documents automatically
use Source editing to preserve their markers. Switching modes retains unsaved text,
but rebuilding formatted content after source edits resets rich-edit undo history.

On desktop, the magnifying glass in the top toolbar (or Ctrl+F / Command+F) opens
**Find in this page** above the document. Matches highlight as you type, with a
match count and Previous/Next buttons that wrap through the page. Close or Escape
clears page-search highlights and its selected match while preserving manual selections.
Up to 5,000 matches per search are highlighted; `+` marks that limit. Find is literal and case-insensitive. Replace
controls appear only while editing; Replace all is one undo step. Preview-only windows do not offer write actions.

## Edit properties

A leading YAML block appears as properties. In Formatted mode, add/edit/remove a
property, or use **Edit YAML…** for the raw header. The first property can be added
through the properties menu even when the empty panel is hidden.

Basic text, lists of text, numbers, booleans, ISO dates and date-times have field
editors. Nested mappings, tags, anchors and complex values remain raw YAML. The
built-in parser implements a subset of YAML; it does not validate the full language.
Use Source/raw YAML when a value is too complex for a field editor.

Body editing retains frontmatter, and a basic property edit patches that field's
lines while preserving unrelated text. Invalid properties remain visible with an
error. An unclosed header switches to Source so editing cannot consume the body.
Dates use `YYYY-MM-DD`; names must be unique and nonempty.

## Save without losing changes

Use Save or Save As explicitly; there is no autosave. An asterisk marks unsaved
changes. Closing, opening another document or leaving a modified document can offer
Save, Discard or Cancel. Cancel keeps the document available.

Saving replaces the destination atomically. A failed save retains the original and
unsaved text. If the loaded file changed on disk, saving over it is refused: use
Save As to keep your version, or reopen after preserving any work you need. This
check is not a file lock. Symlink save destinations are refused.

Edited documents use UTF-8, retaining a UTF-8 BOM and uniform CRLF endings when
present; other endings may normalize during editing. Save As changes the base
folder used for relative links. It does not rewrite all authored links for you.

## Render diagrams

Mermaid fences initially remain readable code. Choose **Diagrams** in Read mode or
**View → Render Mermaid diagrams** to use an installed local Mermaid CLI (`mmdc`).
Your application/environment must make that executable available; opening a document
does not download it or send diagrams to a hosted service.

Rendering processes up to 12 diagrams per document, with a 20-second timeout per
diagram. Unsupported configuration/external-resource declarations, oversized input
or rendering failures leave code visible with an explanation. Generated images stay
in memory and never replace authored Markdown. Render again after changing the theme
if that theme's image has not been generated. Temporary rendering files are cleaned up.

## Read aloud

Click the speaker icon to open Read aloud and press Play. Language defaults to
**Automatic (detect text)** and chooses an installed voice for the passage’s
language locally. You can choose a language and voice manually. A selected passage takes
priority; otherwise playback starts from the visible reading area. Speech follows
the rendered reading view: links read their visible labels without the underlying
destinations, and formatting markers are omitted. URLs and code written visibly
in the document remain readable. The same button
changes to Pause while speaking and Resume while paused. Engines without pause/resume
support disable it during playback; Stop remains available. The speed slider snaps
from 50% to 200% in 25% steps, with gray limit labels and the selected percentage.
Actual speed depends on the native speech engine. Sleep timer offers Off, 15, 30,
45 or 60 minutes. Its bold countdown runs only while speaking. The circular-arrow
reset icon restores the selected duration while preserving playback/pause state.
At expiry, capable engines pause; other engines stop. Play starts a fresh timer.
The playback row is backward 15 seconds, Play/Pause, forward 15 seconds and Stop.
Language and voice controls remain below the playback section. Click outside the popup to hide its controls while playback continues;
click the speaker to toggle the panel open or closed. Back/forward estimate a
15-second jump; each jump clears the previous speech highlight before showing the
new word, including mirrored reader panes. Unrelated search/selection marks are
preserved. Highlights may use estimated timing where word events are unavailable.

Playback stops when content is replaced, editing begins or the
reader closes. Speech does not edit the file. If no engine/voice is available, the
panel explains the problem; available voices depend on the operating system.

## Troubleshooting

- **No Edit/Save:** the host opened a preview-only reader; editing is an explicit option.
- **A link fails:** check the relative path, heading and file encoding; no vault-wide
  filename search is performed.
- **Formatting changes after editing:** use Source for syntax Qt cannot round-trip.
- **Diagram remains code:** check for a local renderer, its error, the timeout or
  unsupported diagram resources. The document remains readable without rendering.
- **Save blocked by external edits:** preserve your version with Save As before reloading.

[Developer integration](../../development/reference/ui/markdown/markdown.md) · [All shared guides](../../development/overview.md#shared-component-user-guides)


Hosts may supply a shared storage browser for Open and Save As. Private storage
can keep text and embedded images in memory, with Save/Discard/Cancel on close
and no persistent private drafts. The host decides which locations are available
and whether opening another document uses a new window. Save failures retain your
current buffer; inspect a reported saved destination before retrying Save As.

## Documentation Library

A host can open a Markdown directory as a wiki. Arrow keys in the left tree open
the highlighted page immediately; Cancel on an unsaved edit restores the current
page selection. A page named after the root folder becomes the single top entry,
with the rest of the documentation nested beneath it. Use the left tree to browse nested
folders and pages. On desktop, **Documentation Library** search filters pages across the library;
its file names/titles or page text selector appears only while a query is entered.
Opening a result highlights matching text in the document and scrolls to its first
match. File-name-only matches may have no matching text in the page. Library marks
remain while the library query is present, independently of **Find in this page**.
The file tree and document share the same bottom edge; empty notices take no space.
Folders with a same-named Markdown file open that page. Its first body heading (after optional YAML properties and blank lines)
becomes the label; otherwise the folder name is used. Expanding the folder still
shows its other pages. Clear search to see the full hierarchy again. Page changes
use the usual unsaved-edit confirmation. Reopen the wiki to discover files added
outside the viewer.

The top bar provides Back, Forward and Up. Back/Forward revisit pages you have
opened. Up opens the containing folder's same-named Markdown page; from that
folder page it opens the parent folder's page. At the documentation root,
README.md or index.md can serve as the folder page. Up is disabled when that
folder has no page or you are already at the root page.

In desktop reading mode, hover a local Markdown/text/code link to see a compact
preview. Markdown targets render with the reader’s heading, emphasis, list
and table styling; text and code targets show their literal source in monospace.
Embedded images are not loaded. Moving off the link closes it immediately.
This does not open the file or change your reading history. Editing mode does
not show hover previews. Missing, binary and external web links have no preview.

A folder opens its same-named page (for example, `banana/banana.md`). Guides
begin with a title heading, which also names them in the tree. A link to another
documentation wiki changes the sidebar to that guide's files. Back and Forward
return to the corresponding guide and tree. Search clears on a scope change.

Floating Contents and reading appearance panels close when you click outside them
or click their toolbar button again.

## Images and animated GIFs

Local GIF images animate in Read mode and the Formatted editor. Images fit within
the page width and reflow when the window changes size. Use ordinary
Markdown image references such as `![Demo](../../../ui/markdown/user_docs/assets/demo.gif)`; relative paths resolve
from the Markdown file’s folder. Playback pauses while that view is hidden.
In Read and Formatted modes, following text keeps normal paragraph spacing
even when the embedded image is tall.

Drag image files from your file browser into either editor to insert them at the
drop position. Formatted mode displays the image immediately; Source mode inserts
its editable Markdown reference. Saved documents use relative paths where possible,
including paths to sibling folders. Spaces and special path characters are encoded
automatically. Drops into unsaved documents use absolute file URLs.
Images remain in their original locations; move them together with the document
when sharing relative references. A drop can be undone in one step.

Use Obsidian image embeds such as `![[assets/demo.gif|400]]` or standard Markdown
`![Demo|400](../../../ui/markdown/user_docs/assets/demo.gif)` to request a width in pixels. Add `|400x200` for
an explicit width and height. Both forms shrink proportionally if needed to fit
the page; smaller images stay small. The source size survives editing and saving.
Obsidian targets may contain spaces and `#`, for example `![[photo #1.png|400]]`.
PNG, JPEG and WebP share the same panel-width and paragraph-spacing rules as GIF.
Code examples and escaped embeds remain literal.

Storage-provider documents keep their existing resource-loading policy; local file
drops and direct GIF decoders are disabled for those documents.


Documentation Library uses heading titles for navigation. Its sidebar never creates,
renames or moves files, including when page editing is enabled with Alt/Option.
Hosts that need filename-based note organization supply their own Notes Library
workspace rather than changing documentation navigation.
