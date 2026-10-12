# Shared code editing components

[User guide](user_docs/README.md) · [Developer API map](../../docs/developer/public-apis.md)

`CodeEdit` is a reusable `QPlainTextEdit` with a palette-aware gutter, current-line
and bounded bracket emphasis, indentation, optional pairing, font zoom and undoable
line commands. It owns no file paths, window/session policies or application preferences.
Existing `TextFileEditor`, INI editor and Markdown widgets are unchanged.

```python
from commonUtils.ui.code_editor import CodeEdit
editor = CodeEdit(parent)
editor.setPlainText(source)
editor.indent_width = 4
editor.use_tabs = False
```

`search.SearchPanel.set_editor(editor)` binds an active document. The panel uses
existing `OperationProgress` ownership for debounced worker searches, rejects
stale results and applies replacements on the GUI thread. Call `prepare_close()`
and wait for `idle` if it returns False before destroying a host. Regex replacements
support numeric/named captures; Replace All is one undo block. Pattern and match
limits prevent unexpectedly expensive searches from becoming an unbounded UI task.

`syntax.SyntaxHighlighter(editor, language)` optionally uses Pygments; applications
supply that dependency. The tested Logistics pin is 2.19.2. Plain text requires no
lexer. RegexLexer states propagate between blocks; other lexer families use a
bounded per-block fallback. Long blocks and large documents skip highlighting.
See the included Pygments BSD license and the implementation notes in the module.

`commonUtils.persistence.text` supplies Qt-independent BOM/encoding handling, text/binary
sniffing, normalized text snapshots and atomic conflict-checked byte writes. Use
explicit codecs for ambiguous legacy encodings and retain snapshots until save.
No existing File class is changed or automatically coupled to an editor.


## Extended editing components

`CodeEdit.transform(command)` applies undoable line/selection transformations;
`transforms.transform_lines` is Qt independent. `formatting.validate_text` and
`format_text` are bounded JSON/XML utilities. JSON output preserves lexical tokens;
XML rejects DTD/entity declarations and refuses formatting mixed content, CDATA
and xml:space-preserved content. Validation/formatting is limited to 1,048,576 Python characters (the UI labels this
“1 MiB of text”).

`CodeEdit` supports bounded multi-cursor editing via `set_cursors`,
`add_next_occurrence`, `rectangular_selection` and `clear_extra_cursors`. Alt-click
adds cursors and Alt+Shift-drag selects columns. Paste distributes matching line
counts across cursors. Qt cursors retain UTF-16 positions, edits form one undo block,
and foreign document changes retire extra cursors. There is no virtual-space padding.

`EditorViews` owns two editors with one shared QTextDocument and independent
navigation. Its `active` editor follows focus. `set_split(Qt.Orientation.Horizontal)`
creates side-by-side views, Vertical creates stacked views, and None removes the
extra view. Read-only state and folding are shared. File/session policy remains
with the caller. `folding.fold_ranges` is a pure bounded structural region finder;
fold markers and indentation guides follow the editor palette.

`diff.compare_text` returns a bounded text diff model; `DiffDialog` shows read-only
side-by-side and unified views. An optional application callback applies a selected
change. `apply_change` rejects stale buffers and returns Python-character offsets
and replacement text; callers convert offsets to Qt positions and own undo/save
policy. Limits are 1,048,576 Python characters and 5,000 lines per side (the UI calls the
character limit “1 MiB”).

Outside this package, `ui.command_palette` searches/configures caller-owned QAction
mappings. It imports no application feature modules. `persistence.session.SessionStore`
provides bounded, atomic, private JSON checkpoints without Qt; callers own record
schemas, live-instance locking, restoration and worker policy.


## Diff and merge review

`DiffDialog` now uses resizable panes, syntax highlighting, linked scrolling,
connecting change bands and per-hunk arrows. Apply callbacks may return the new
buffer text to refresh the comparison immediately; callbacks returning `None`
retain the older reopen-after-apply behavior. The host still owns stale-buffer
checks, conversion from Python offsets to Qt UTF-16 positions, undo and saving.

`commonUtils.persistence.merge.merge_text(base, left, right)` builds a Qt-independent,
bounded three-way model. `MergeSession` owns live result ranges and a bounded
undo/redo history that includes manual edits and resolution decisions. Independent
and identical changes can be applied together; overlapping edits remain explicit
choices. Adjacent insertion boundaries are grouped conservatively.

`MergeWidget(model, left_name=..., right_name=..., path=...)` is an embeddable widget
with independent read-only sources and an editable result. `MergeDialog` supplies
an optional Apply callback. Use Left, Right, Both (left then right), Keep Base, or
edit the result and mark the selected change resolved. Apply is available once all
changes are resolved. Blue marks modifications, green additions, gray deletions,
and red unresolved conflicts; colors adapt to the palette. The ancestor can be
shown separately. Cancel discards the merge session without invoking the host.

Inputs should be normalized text snapshots from `persistence.text`. The model
limits each input/result to 1,048,576 Python characters and 5,000 lines; Git callers
also bound raw blob bytes. Hunk rendering supplies character emphasis for short
regions. `diff_bands` provides the extracted unified-patch renderer and dual
line-number gutter for consumers with patch presentation models.

Filename detection recognizes `.pyi`, PHP with embedded HTML, and case-insensitive
`.blade.php` compound names. Blade uses a small directive/interpolation layer over
Pygments HTML/PHP grammars; multiline Blade constructs use the bounded per-line
fallback and are not parsed as a complete template. Both light and dark palettes
use the same shared highlighter. Hosts need no separate language definitions.

PHP/HTML mode carries both Pygments grammar states across blocks, so a PHP opening
tag on one line still highlights declarations on subsequent lines and resumes
HTML formatting after the closing tag. Blade retains its documented per-line
delegating fallback.

## Shared view lifecycle

`CodeEdit.share_document_from(source)` attaches another CodeEdit to the same
QTextDocument and copies font, indentation, comment, gutter, wrapping and read-only
settings. It reconnects multicursor/folding hooks without duplicate registrations.
It does not copy cursor/scroll position or continually synchronize preferences.
The host must retain the document owner for as long as any view uses the text.

`CodeEdit.detach_document()` disconnects the old editing hooks and gives the view
an empty, owned plain-text document. Call it before deleting a shared view; the
view can also be attached again. File identity, unsaved prompts and deciding when
the last buffer can be deleted remain host responsibilities. EditorViews uses
these APIs for its own split lifecycle.

`SyntaxHighlighter.rebind_editor(editor)` moves palette observation to another
view of its existing document. Rebind before detaching/destroying the old view.
The highlighter and its timer remain owned by the document/highlighter, and the
lexer instance is retained. A different document raises ValueError. This changes
neither document ownership nor text, undo history or cursor positions.

The Qt-independent merge model is imported directly from
`commonUtils.persistence.merge`. The former `ui.code_editor.merge_model` forwarding
module has been removed; hosts use the persistence owner for `merge_text`,
`MergeModel`, `MergeRegion` and `MergeSession`.
