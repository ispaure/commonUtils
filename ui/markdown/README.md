# Markdown viewer and editor

`commonUtils.ui.markdown` uses Qt's Markdown/rich-text renderer for headings, lists,
tables, fenced code, local images and links, without a web-engine dependency.
Holding **Alt** while opening a standalone window enables editing centrally;
buttons and other callers need no modifier handling. Otherwise documents open in
preview-only mode by default, with no Edit toggle or write
actions. Pass `allow_edit=True` to `open_markdown`, `MarkdownWindow` or
`MarkdownViewer` to offer editing for that window/widget; the option stays in
effect across link navigation and Open. Editing-enabled windows start in Formatted edit mode. **Read** switches to preview
and **Edit** returns to same-pane editing:
headings, emphasis, lists, links and tables remain rendered while editing. The
**Formatted / Source** selector also provides precise Markdown source editing.
**Read** returns to the rendered read-only document, including unsaved changes. Requires PySide6 and an existing
QApplication, as described in [Qt application setup](../README.md#pyside-application-setup).

```python
from commonUtils.ui.markdown import MarkdownViewer, open_markdown

# Preview-only window; the helper retains it until closed.
window = open_markdown('docs/index.md', parent=application_window)

# Explicitly permit editing, or embed an editing-enabled widget.
editable_window = open_markdown(
    'notes/index.md', parent=application_window, allow_edit=True)
viewer = MarkdownViewer('docs/index.md', parent=application_window, allow_edit=True)
layout.addWidget(viewer)
```

`open_document(path, fragment='')` returns whether navigation succeeded.
`current_path` provides the displayed document path; `path_changed(Path)` signals
successful loads/saves (or `None` for a new untitled document). Relative file links resolve from the current document, including
encoded spaces and `#heading-fragments`. Headings receive GitHub-style anchors,
with duplicate headings suffixed `-1`, `-2`, and so on. Back/Forward (Alt+Left /
Alt+Right) restore document history and scroll positions. Navigating after going
Back discards the abandoned forward branch. Navigation buttons use the same native
Qt icons and shared control as FileBrowser.

Standard `[label](https://example.com)` links and local `[[Page]]`, `[[Page|Label]]` or
`[Page|Label]` aliases are supported in reading and formatted editing. Aliases
resolve relative to the current document, adding `.md` when no extension is given;
`[[Page#heading|Label]]` also works. Explicit Markdown destinations retain their
extension as written. Code examples and escaped links stay literal. In formatted
editing the cursor reveals link syntax; Ctrl/Cmd-click follows a link. Ordinary
clicks place the cursor for editing. Source is retained as authored when saved.

**Contents** opens a floating list at the right side of the toolbar, with indented
headings/subheadings and links to their anchors. It closes after a selection, Escape,
or clicking outside. It reflects unsaved edits and heading jumps participate in
Back/Forward history in reading mode. Choosing a heading while editing formatted
text keeps that editing mode and moves its cursor to the heading. Choosing one
from source mode switches to reading without discarding edits.

### YAML properties (frontmatter)

A `---`-delimited YAML mapping at the very beginning of the document appears in a
**Properties** panel above the body, following
[Obsidian's frontmatter convention](https://obsidian.md/help/properties). Properties
are excluded from body rendering and the table of contents. Reading shows values;
formatted editing enables **+ Add property**, double-click/**Edit**, **Remove**,
checkbox controls and **… → Edit YAML…**. Right-click a row for the same property
actions. Edit/Remove are enabled when a row is selected. Empty property panels
stay hidden, including empty frontmatter; the toolbar's corner **… → Add YAML
property…** creates the first field. Its **Edit YAML…** action also opens the raw
header editor. These actions are enabled only in Formatted edit mode. Parse errors
stay visible even when no rows can be displayed. Source mode still exposes the complete file.

Supported property editors include text, lists/tags (one text item per line),
numbers, booleans, ISO dates and date-times. Nested mappings, non-text list items
and tagged/complex values remain raw and use the YAML/source editor. There is no vault-wide type registry,
Obsidian indexing or vault-wide file search. Property names must be unique nonempty
strings. Dates use `YYYY-MM-DD`; date-times use ISO format.

Body edits preserve the frontmatter text, including comments and quoted/multiline
values. Editing a basic property patches only that property's lines; unrelated
fields, comments and the Markdown body remain unchanged. Complex values such as
nested maps, block scalars, anchors and tags are kept as raw YAML and can be edited
with **Edit YAML…** or Source mode. Invalid basic syntax is shown with an error and
retained during body edits. An unclosed block switches to Source mode so formatted
editing cannot swallow the rest of the document.

There is **no YAML dependency**. The built-in parser supports a deliberate subset:
plain/quoted text, true/false, null, decimal numbers, ISO dates/date-times, simple
inline lists and dash lists. It checks duplicate names and common syntax errors;
it does not fully validate complex YAML, resolve aliases, interpret custom tags,
or implement the complete YAML specification. Complex input stays raw rather
than being coerced into basic fields. Arbitrary object constructors are never run.

```python
from commonUtils.markdownUtils import split_frontmatter, parse_properties, replace_property

text = '---\ntitle: "Example"\ntags: [docs]\n---\n# Body\n'
parts = split_frontmatter(text)
assert parse_properties(parts)['tags'] == ['docs']
updated = replace_property(text, 'published', True)
assert split_frontmatter(updated).body == parts.body
```

### Typed Markdown and selection wrapping

Formatted mode follows the [Obsidian Live Preview rule](https://obsidian.md/help/edit-and-read)
for supported inline spans: hide Markdown markers outside the active span and show
them when the caret is inside it or the selection overlaps it. This includes the
position immediately after the last letter, before the closing marker. Moving or
selecting does not change the text, dirty flag or undo history. Heading prefixes
also appear on the active heading. Inactive heading prefixes have zero horizontal
advance, including their trailing space. Active link text and delimiters are white;
inactive links retain their normal link styling. Bold/italic remain styled while their delimiters
are visible; incomplete delimiters remain plain so they can be repaired.

Supported emphasis uses `**`/`__`, `*`/`_` and combined triple markers. Inline code
supports single/double backticks. Typed spellings remain editable; loaded Markdown
can be normalized by Qt when rich formatting is materialized. Escaped syntax is
kept literal, and code payloads do not interpret emphasis. Source mode shows all
syntax and remains preferable for unsupported extensions or exact round trips.

Backspace/Delete edit the actual visible delimiter at the caret. For example,
removing one closing star from `**bold**` leaves plain `**bold*`; completing it
restores the style. Interior content edits keep valid surrounding syntax. Undo
restores the exact text. No whole-document reload occurs during typing/navigation.

Triple-backtick or tilde fences support multiline code, including an optional
language label such as `python`. Fences are visible when the caret/selection enters
the code region and hidden outside it. Unfinished fences remain editable without
an automatically added closing fence. The code uses a monospace font; language
labels are preserved rather than providing a syntax-highlighting engine. Existing
tables stay independent of fence edits, including incomplete fences nearby.

With text selected, `*`, `_` or a backtick wraps/formats the selection instead of
replacing it. One star/underscore applies italic; pressing it a second time with
the selection still active applies bold. In Source mode the corresponding delimiters
are inserted on both sides (`*text*`, then `**text**`). The selection remains active.
Typed conversion/wrapping is undoable with the triggering input, without rebuilding
the entire document or losing tables and other blocks. Saving remains explicit.

### Table editing

In Formatted editing, use **Table** on the formatting toolbar or right-click in
the document. **Insert table…** asks for rows (including the header) and columns.
With the caret in a cell, add rows above/below, columns before/after, delete the
current row/column, or delete the table. The first row is the Markdown header;
deleting it promotes the next row. Removing the last row/column removes the table.
Other cells and surrounding document content are retained. Each operation is one
undo step and is saved as Markdown with the normal explicit Save action.

Structural actions are disabled outside a table, for selections spanning content,
in Source mode and in preview-only viewers. Insert is available outside tables;
nested rich-text tables are not offered. Source mode still permits direct pipe-table
editing. Adding a column does not merge cells or change the surrounding body/YAML.

### Editing and saving

Standalone windows provide File/Edit/View menus using the platform's normal menu
placement (the system menu bar on macOS). The toolbar does not display a filesystem path; the title uses the
document filename. Preview-only windows retain Open, Close, Copy, Select All, Find
and Contents; write actions and Replace controls are hidden/disabled.
With `allow_edit=True`, windows provide **File → New / Open / Save / Save As / Close** and an
Edit menu with Undo/Redo, Cut/Copy/Paste, Select All and Find/Replace. The widget owns reusable actions
(`new_action`, `open_action`, `save_action`, `save_as_action`, `find_action`, etc.)
that embedding applications can put in their own menus. Standard platform shortcuts
are enabled (Command on macOS); Ctrl+N, Ctrl+O, Ctrl+S, Ctrl+Shift+S and Ctrl+F
also work explicitly. Both editors support native selection, clipboard and undo/redo.
The formatting toolbar supplies bold, italic, inline code, links, headings, bullet
lists and quotes. Ctrl+B/Ctrl+I format text; Ctrl+K inserts a link. Find works in
reading and both editing modes; Replace/Replace all operate on the active editor. Search
is literal and case-insensitive; Replace all is one undo step.

```python
viewer.set_editing(True)  # Same-pane formatted editing is the default.
# viewer.formatted_editor is the editable QTextEdit.
viewer.set_edit_mode('source')  # Optional precise editing in viewer.editor.
# The toolbar formats rich text or inserts source syntax, depending on the mode.
if viewer.is_modified:
    saved = viewer.save_document()  # False on failure/cancel; inline error message.
# An explicit path performs Save As and updates the document's relative-link base.
saved = viewer.save_document('docs/revised.md')
```

`new_document()`, `open_document()` and `save_document()` return success booleans.
A modified document is marked with `*`; `modified_changed(bool)` reports changes.
Leaving a modified document or closing the standalone window prompts for
Save/Discard/Cancel. Reading mode and heading jumps retain unsaved edits in memory.
An embedding application's close handler should call `viewer.can_close()` and
honor a false result before destroying its parent window.

Formatted editing uses Qt's Markdown reader/writer. Entering formatted mode,
viewing contents or saving without changes does not reserialize the source: exact
original bytes are retained. Actual formatted edits convert the document back to
Markdown, so spacing, table alignment, list markers and code-fence spelling may
change. Raw HTML, comments, custom extensions and other unsupported syntax can be
lost during that conversion; use **Source** for documents whose precise syntax
matters. There is no full HTML editor or extension-aware round-trip guarantee.
Switching modes retains text and unsaved status; rebuilding the rich document
after source changes resets its rich undo history. `markdown_text()` returns the
current Markdown, synchronizing formatted edits into the source editor.

Saves stage a file beside the destination, flush it and replace atomically,
preserving existing mode bits. A failed save keeps the original and unsaved edits.
An observed on-disk change prevents saving over the loaded file; use Save As or
reopen. This check is not a filesystem lock and cannot exclude a write racing with
the final replacement. Symlink save destinations are refused. Unmodified saves
retain exact bytes; edited files use UTF-8, preserving a UTF-8 BOM and uniform
CRLF line endings when present. Editing may normalize other line endings or
Unicode line separators through Qt's plain-text editor. Saving is explicit:
there is no autosave.

HTTP/HTTPS and mail links open through the operating system's default application.
Local navigation accepts UTF-8 (optionally BOM-prefixed) `.md` and `.markdown`
files. Missing, unreadable, invalid-text or unsupported linked files show an inline
error while retaining the current page and history. Local non-Markdown files and
other URL schemes are not launched by this reader. Rendering is Qt Markdown;
full web-page HTML/CSS, JavaScript and Mermaid diagrams are not supported.

Internally, `ui/markdown/__init__.py` preserves the public imports; `viewer.py`
owns the embeddable widget and `window.py` the standalone window/lifetime. Editing actions and
mode synchronization are separated from the properties panel. Shared heading
iteration keeps reading and formatted-editor anchors consistent, including names
that collide with generated numeric suffixes. Encoding and atomic file writes
live in the Qt-independent `io.py` helper. `live_edit.py` owns incremental typed
syntax editing and selection wrapping. `syntax.py` shares inline/fence parsing and `links.py` shares link parsing, aliases and preview conversion;
`preview.py` handles cursor-sensitive display without modifying the document;
`document.py` materializes loaded styles and exports syntax while retaining Qt's
links/images/table structure. `formatted.py`, `editing.py`, `headings.py`
and `properties.py` keep mode synchronization, actions, anchors and YAML UI separate. Applications should keep using
`MarkdownViewer`, `MarkdownWindow` and `open_markdown` rather than these internals.

FileBrowser explicitly enables editing (`allow_edit=True`) for registered MarkdownFile activation;
applications may still supply a higher-priority activation handler. Keep feature
user documentation in the consuming application, not the shared library.


Embedded HTML is displayed as literal Markdown in reading and formatted modes.
Qt's HTML-block importer can otherwise silently discard following paragraphs.
Reader layout is finalized before restoring scroll position; regression fixtures
check the final paragraph of long documents in all three modes. Source mode remains
the choice for exact source preservation and unsupported extensions.
