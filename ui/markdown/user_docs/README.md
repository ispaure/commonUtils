# Reading and editing Markdown

The shared Markdown reader opens local `.md` and `.markdown` documents with headings,
links, images, tables and fenced code. It also supports local wiki-style links,
Obsidian-style callouts and a limited YAML properties editor. It is a document
reader/editor, not an Obsidian vault manager: there is no vault search, plugin system
or vault-wide property registry.

## Read and navigate

Use Contents to jump to headings and Back/Forward to return to earlier documents
and scroll positions. Relative links resolve beside the current document. Wiki links
such as `[[Notes|My notes]]` target local documents; extensionless targets gain `.md`.
A similarly named document elsewhere in a vault is not automatically discovered.
Web/mail links open in the operating system's default application. Local non-Markdown
links and other URL schemes are not launched by this reader.

Reading appearance adjusts text from 10–24 pt for the current window without changing
the file or editing font. Reading follows the host's light/dark palette. F11 toggles
fullscreen. Escape closes Contents/Find first, then leaves fullscreen. Missing or
unreadable linked documents show an error and retain the current page.

Callouts display as quote panels. A `+` callout starts expanded; a `-` callout starts
collapsed. Click its title to fold/unfold it. Folding never changes the file. Embedded
HTML is shown literally; this is not a full web-page renderer.

## Choose an editing mode

Some hosts open documents for reading only. Where editing is enabled, **Read** shows
the current rendered document, including unsaved edits, and **Edit** returns to the
editor. Standalone windows can also enable editing when opened with Alt held.

**Formatted** mode lets you edit rendered headings, emphasis, lists, links and tables.
Supported Markdown markers become visible near the caret/selection or pointer so
you can repair syntax. Formatting controls and selection wrapping support common
inline styles. The Table commands insert a table or add/remove rows and columns;
the first row is the header. Structural table changes are undoable.

**Source** exposes the Markdown text. Use it for exact syntax and unsupported
extensions. Actual formatted edits can normalize spacing, list/table/fence spelling
or lose unsupported constructs through Qt's Markdown conversion. Merely reading or
saving without edits preserves the original bytes. Callout documents automatically
use Source editing to preserve their markers. Switching modes retains unsaved text,
but rebuilding formatted content after source edits resets rich-edit undo history.

Find is literal and case-insensitive. Replace operates only while editing; Replace
all is one undo step. Preview-only windows do not offer write actions.

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

Open Read aloud, select a voice/language and press Read. A selected passage takes
priority; otherwise playback starts from the visible reading area. Speed and available
pause/resume controls depend on the native speech engine. Back/forward estimate a
15-second jump; highlights may use estimated timing where word events are unavailable.

Playback stops when content is replaced, editing begins, the panel closes or the
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

[Developer integration](../README.md) · [All shared guides](../../../README.md#shared-component-user-guides)
