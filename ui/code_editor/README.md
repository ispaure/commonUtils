# Shared code editing components

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
and xml:space-preserved content. Validation/formatting is limited to 1 MiB.

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
policy. Limits are 1 MiB and 5,000 lines per side.

Outside this package, `ui.command_palette` searches/configures caller-owned QAction
mappings. It imports no application feature modules. `persistence.session.SessionStore`
provides bounded, atomic, private JSON checkpoints without Qt; callers own record
schemas, live-instance locking, restoration and worker policy.
