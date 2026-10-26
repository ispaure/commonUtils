# Markdown integration

Use `MarkdownViewer` for embedding and `MarkdownWindow` / `open_markdown` for a
standalone or document-hosted window. They render Markdown with Qt without a web
engine. See the [user guide](../../../../user/markdown/markdown.md) for reading, editing, YAML properties,
callouts, local links, optional Mermaid diagrams and speech workflows.

## Internal ownership and embedding contracts

The source editor owns editable text and its undo stack. `document_state`
([MarkdownDocumentState](../../../../../ui/markdown/session.py)) owns the loaded path, exact saved bytes,
rich-import baselines and pending-save flag. It does not duplicate the editable
buffer. Loading/new-document transitions reset rich baselines explicitly.

| Component | Dependencies and responsibility |
| --- | --- |
| [FormattedEditing](../../../../../ui/markdown/formatted.py) | Source/rich editors, mode selector, document state and three callbacks; import, synchronize and format rich edits without knowing the viewer |
| [SearchHighlights](../../../../../ui/markdown/search.py) | Text surfaces, search controls, page stack and library-query callback; scoped transient selections and its parented refresh timer |
| [TableEditing](../../../../../ui/markdown/tables.py) | Rich editor, menu, action factory and enabled predicate; table actions and undo operations |
| Viewer | Document navigation, signal integration, lifecycle and stable embedding entry points |
| Editing/reading helpers | Widget action assembly, save/read presentation and interaction with the viewer's declared state/components |

Three former behavior mixins are now composed components. The remaining two
helpers contain widget integration; they do not own hidden copies of the rich
baseline or search/table state. Widget entry points such as `markdown_text()`,
`set_edit_mode()`, saving and IDE callback hooks remain explicit methods. No
dynamic attribute forwarding is installed.

Viewer construction keeps navigation, text surfaces, document properties and
reading controls in four private builders in `viewer.py`. The constructor retains
wiki composition, signal/lifetime integration, provider action policy and initial
document admission. Builders populate the existing widget fields in construction
order; they introduce no additional state owner or embedding interface.

Hosts which previously assigned `_loaded_path` or `_source_bytes` should assign
`document_state.loaded_path` and `document_state.source_bytes`. A private-document
host discarding its draft calls `document_state.new()` before clearing editor
surfaces. The Notes and IDE consumers exercise these boundaries. Search marks do
not dirty documents, unchanged rich imports do not normalize exact source, and
actual rich synchronization remains one source undo operation.

[Ownership tests](../../../../../tests/markdown/test_markdown_ownership.py) construct rich editing
without a viewer. The existing Markdown/search/table/frontmatter suites exercise
integrated navigation, mode changes, YAML preservation, save conflicts and undo.

## Create and retain a reader

Create QApplication first. This standalone example needs PySide6:

```python
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import open_markdown

app = qt.initialize_q_app()
window = open_markdown(None, allow_edit=True)
app.exec()
```

A concrete path opens a local UTF-8 `.md`/`.markdown` file. `None` with editing
creates an untitled document. `open_markdown` retains its window until destruction
and routes through the optional document host; `detached` and `allow_new_tabs`
control that hosting request. It returns the window.

`MarkdownViewer(path=None, parent=None, allow_edit=False)` is an embeddable QWidget.
Preview-only is the default. `allow_edit=True` adds editing actions and starts in
Formatted mode where supported. Holding Alt when constructing MarkdownWindow also
enables editing; the bare viewer's option remains explicit. FileBrowser opts into
editing for registered MarkdownFile activation; feature activations can override it.

## Navigation, editing and close contracts

`open_document(path, fragment='')`, `new_document()` and `save_document(path=None)`
return success booleans. Failures/cancel return false and leave an inline message
where applicable. `current_path` and `path_changed(Path or None)` identify the
current document; `is_modified` and `modified_changed(bool)` expose dirty state.
Relative links use the loaded/saved file's parent; Save As updates that base.

`set_editing(True)` enters editing; `set_edit_mode('source')` selects raw text.
`markdown_text()` synchronizes formatted edits and returns the current source.
`viewer.editor` is the source editor; `formatted_editor` is the rich editor.
Reusable actions such as `save_action`, `find_action` and `open_action` can be placed
in host menus. Source replacement can reset rich undo history.

Formatted syntax reveal follows the caret (including element boundaries) and
overlapping selections, never pointer hover. Active link text uses the palette's
Text color. Link labels activate on click release; revealed syntax remains editable,
and Ctrl/Command-click activates from anywhere in a link. New document loads reset
reading selections; rerendering the current document preserves them.

An embedded host must call `can_close()` before destroying/replacing the viewer,
honor false, and stop its speech/optional diagram work when performing custom
shutdown. MarkdownWindow handles those duties for its own close event. Document
hosts must preserve close vetoes through [document-host routing](../workspaces.md).

## Source and save guarantees

Qt presentation first classifies each block's fragments into a named internal
content record: callout title/separator, inline-code ranges and image presence.
The existing traversal retains quote-depth scope and format precedence; code and
image helpers apply native typography without becoming source-editing owners.
`document.materialize_formats` separately traverses rich blocks, plans authored
inline delimiters and code fences, then applies replacements in reverse position
order. Code-fence planning also clears the original rich block flags before those
replacements. UTF-16 positions, undo handling and source synchronization retain
their existing contracts.

Reading, callout folding and unchanged saves do not reserialize original bytes.
Actual formatted edits use Qt's Markdown writer and can normalize or lose unsupported
syntax. Source is the precise editing route; callout documents automatically select
it. Supported live inline/fence editing keeps typed spellings while editing; that is
not a full extension-aware round-trip guarantee for arbitrary documents.

Frontmatter handling is separate from the body. Basic property patches preserve
unrelated header lines/body; complex YAML remains raw. The built-in parser has no
YAML dependency and implements a deliberate subset, not full YAML validation or
object construction. An unclosed frontmatter block forces Source mode.

Saves stage beside the destination, flush and atomically replace, preserving mode
bits. Changed-on-disk files and symlink destinations are refused. Conflict detection
is not a writer lock. Edited content is UTF-8 with UTF-8 BOM/uniform CRLF retention
where present; other line endings can normalize in Qt. Failed saves retain edits.

## Rendering and optional services

Local navigation accepts Markdown, including relative/wiki aliases and heading
fragments. It does not search an Obsidian vault. HTTP/HTTPS/mail links use the OS;
unsupported local types/schemes do not launch. Embedded HTML remains literal.
Reading appearance affects the reading pane only, not authored content/editor fonts.

Reading code fences use continuous padded monospace panels with language labels
painted outside the document text. Three or more backticks are supported by the
existing Qt Markdown parser. Reading-only syntax colors use Pygments when it is
available, including `vbnet`; unknown languages and installations without Pygments
keep plain monospace text. Token offsets account for UTF-16, including emoji.
Highlighting is bounded to 64 KiB characters per block group. This does not change
stored Markdown, formatted edit serialization or source-editor highlighting.

Mermaid is an explicit optional local QProcess operation using `mmdc`, never an
opening-time download. It has bounded input, per-diagram timeout, bounded image
size/cache and source-preserving failure. Closing/replacing the document cancels
work. See [diagram behavior](../../../../user/markdown/markdown.md#render-diagrams).

ReadAloud initializes native QtTextToSpeech on demand. The viewer supplies visible
text/selection and stops on replacement, editing or close. Native backend and voice
availability are platform-specific. Custom hosts must retain the same lifecycle.

## Maintenance boundaries

`viewer`/`window` own widget/window lifetime; `io` owns Qt-independent loading and
atomic saves. `editing`, `formatted`, `properties` and `tables` own edit behavior;
`syntax`, `links`, `live_edit`, `preview` and `document` handle syntax/display/export.
`reading`, `presentation`, `extensions` and `diagrams` own reading presentation.
These internals are not alternate embedding entry points. Test source preservation,
UTF-16 selection accounting, heading collisions, last-paragraph visibility, external
save conflicts and process/speech retirement when changing them.

[UI overview](../ui.md) · [Developer hub](../../../development.md)

Formatting actions share the existing navigation row through a compact Format
menu. Table actions remain attached to the formatted editor and update their
enabled state from its current selection; no second formatting row is reserved.

## Provider-backed documents

`MarkdownViewer` and `MarkdownWindow` accept `storage=` for virtual documents.
See [resource provider contracts](../resource-providers.md#markdown-storage) for
byte I/O, conflict checks, asynchronous completion, resource loading and private
presentation. Hosts own providers and worker lifetimes; the shared viewer has no
backend-specific credential or encryption dependency.

## Directory wiki mode

Pass `directory=Directory(Path(...))` (or a path) to `MarkdownViewer`,
`MarkdownWindow` or `open_markdown`. This adds an inline left tree and search;
without it the existing single-document layout is unchanged. With no initial
path, the directory's same-named `.md`, `README.md`, `index.md`, or first available
page opens. An empty directory leaves the viewer empty.

`formats.markdown.wiki.MarkdownWiki` owns the GUI-free catalog used by native
mobile consumers too. It traverses visible directories, skips symlinks and reads
UTF-8 Markdown files up to 1 MiB. Read failures are retained in `errors` for inline
reporting. Searches use a case-insensitive substring over names/titles or source
text and retain matching ancestors. Folder landing files match the folder stem
and are not duplicated among children. The first nonblank body line can supply an ATX or Setext heading title, including
after a complete YAML frontmatter block. Introductory body text prevents title
adoption; unclosed frontmatter falls back to the file/folder name.

Tree clicks call the existing `open_document`, preserving save/discard/cancel and
history. Links and Back/Forward synchronize the tree selection. The catalog is a
snapshot taken when the view opens; reopen it to include files added externally.
`storage` adapters with a directory must provide locally catalogable paths;
directory mode does not enumerate private or remote storage adapters.

Wiki mode uses arrow icons for Back/Forward and adds an Up arrow with a tooltip. Up uses
`MarkdownWiki.parent_page` and calls `open_document`, including its unsaved-edit
veto. Articles go to their containing folder's same-named page; folder landing
pages go to their parent's landing. The root also accepts README/index. Missing
landing pages disable Up, and navigation stays inside the catalog root.

Relative page links resolve from the current source file, including `../`.
An extensionless destination tries `.md` and `.markdown`; a directory tries its
same-named page, README, then index. Linked Markdown may be outside the tree and
still participates in page history. Explicit local text/code links open the host
text editor separately and never enter wiki history; missing and binary files
report an inline error. Files are never executed.

For ordinary local documents the Qt reader calls `ui.text_editor.open_text_file`.
A host can install `QApplication._commonutils_open_text_file(path, parent)` to use
its own editor; otherwise a retained `TextFileWindow` opens the shared editor and
honors unsaved-change cancellation. Storage-backed readers retain their adapter's
`open_link` routing and do not use raw local-file handoff.

## Reading-mode link previews

`LinkPreview` in `hover.py` observes the reading browser's viewport. Pointer moves
on local file links resolve through the same extensionless/folder resolver as
navigation and show a nonactivating, pointer-transparent tooltip window. Previews
read at most 16 KiB and display at most 18 source lines/2,400 characters. They do
not navigate, execute code, load resources or create editor sessions. Nonlocal,
missing, binary and storage-adapter links show no preview. Protected local roots
use the existing access check.

Leaving the anchor/viewport, scrolling, pressing a mouse button, replacing the
document, hiding/deactivating the view or entering edit mode immediately hides
and clears the snippet. Editing widgets have no hover-preview filters.

## Wiki scopes and landing pages

A conventional wiki has a `docs/docs.md` scope landing, audience subfolders and
same-named nested pages such as `banana/banana.md`. Start pages with an H1 after
optional YAML properties; the heading supplies the visible title. Parent pages
should link to their children so the hierarchy also works outside the viewer.

Explicit Markdown links into another wiki replace the sidebar catalog with that
wiki's scope. Back and Forward restore the destination's scope as well. Search
clears when changing scopes so a previous query cannot hide the new guide.
`formats.markdown.wiki.documentation_root(path, fallback)` resolves conventional
scopes without application-specific ownership rules. Custom directories retain
the supplied root while browsing contained pages. This is navigation scoping,
not an access boundary; normal local-file access checks still apply.

## Animated images and file drops

Local GIF image resources use retained `QMovie` decoders in the reading browser
and formatted editor. Frames update the document resource cache and invalidate
layout painting without changing Markdown, the dirty flag or undo history. Hidden
surfaces pause playback; removing images or navigating retires unused decoders.
Relative resources resolve through the document base URL. A retained image object
handler caps drawing at the page width and scales both dimensions together,
including explicit `|widthxheight` hints. Resizing does not mutate image formats,
source, dirty state or undo history. Obsidian `![[image.gif|400]]` and standard
`![Caption|400](../../../../../ui/markdown/image.gif)` hints share `formats.markdown.images.image_size`;
wiki embeds retain their exact source through formatted editing/export. Direct animation loading
respects protected local roots and never bypasses a supplied resource loader.
Provider-backed resources retain their existing static rendering contract.
Obsidian image targets can contain literal spaces and `#` in filenames, including
PNG/JPEG/WebP images; the importer encodes these for Qt without altering saved source.

Image paragraphs use text-based minimum line heights in Read and Formatted modes,
including table cells, so paragraph leading does not multiply the image height.
Text-only paragraphs retain proportional leading.

Local image-file drops insert Markdown references in Source mode and image formats
in Formatted mode, with one undo operation per drop. The viewer supplies the saved
document folder for relative paths; unsaved documents and separate Windows drives
use absolute file URLs. Files are referenced in place. Provider-backed documents
disable this local-file insertion path. See the [user guide](../../../../user/markdown/markdown.md#images-and-animated-gifs).


`WikiPanel` presents a **Documentation Library** with heading-based page titles.
The tree explicitly disables drag/drop and item editing; `allow_edit` affects the
page editor, not library structure. Native `MarkdownWikiView` uses the same
Documentation Library label and catalog title rules. These shared viewers do not
own notes/vault file organization; consumers implement that workflow.
