# Markdown integration

Use `MarkdownViewer` for embedding and `MarkdownWindow` / `open_markdown` for a
standalone or document-hosted window. They render Markdown with Qt without a web
engine. See the [user guide](user_docs/README.md) for reading, editing, YAML properties,
callouts, local links, optional Mermaid diagrams and speech workflows.

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

Mermaid is an explicit optional local QProcess operation using `mmdc`, never an
opening-time download. It has bounded input, per-diagram timeout, bounded image
size/cache and source-preserving failure. Closing/replacing the document cancels
work. See [diagram behavior](user_docs/README.md#render-diagrams).

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

[UI overview](../README.md) · [Developer hub](../../docs/developer/README.md)

Formatting actions share the existing navigation row through a compact Format
menu. Table actions remain attached to the formatted editor and update their
enabled state from its current selection; no second formatting row is reserved.
