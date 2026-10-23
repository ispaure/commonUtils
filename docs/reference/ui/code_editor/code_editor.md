# Shared code editing components

[User guide](../../../user/code_editor/code_editor.md) · [Developer API map](../../../developer/public-apis.md)

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

`commonUtils.formats.code_syntax.syntax_style(dark=False)` supplies the shared
Pygments style for Qt highlighting, native `formats.code_spans.syntax_spans`, and
Markdown reading code blocks. It loads Pygments only on demand. Accents use muted
orange keywords in dark mode and blue keywords in light mode, green strings,
blue numbers, purple built-ins and italic gray comments. Ordinary identifiers,
module paths, function names, operators and punctuation inherit host text colors;
the style does not apply a document foreground or background. Qt chooses the
variant from the editor's Base palette and refreshes after palette changes.

`commonUtils.persistence.text` supplies Qt-independent BOM/encoding handling, text/binary
sniffing, normalized text snapshots and atomic conflict-checked byte writes. Use
explicit codecs for ambiguous legacy encodings and retain snapshots until save.
No existing File class is changed or automatically coupled to an editor.


## Extended editing components

`CodeEdit.transform(command)` applies undoable line/selection transformations;
`transforms.transform_lines` is Qt independent. `formatting.validate_text` and
`format_text` are bounded JSON/XML utilities. JSON output preserves lexical tokens;
XML rejects DTD/entity declarations and refuses formatting mixed content, CDATA
and xml:space-preserved content. Validation/formatting is limited to 1,048,576 Python characters.

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
policy. Limits are 1,048,576 Python characters and 5,000 lines per side.

Outside this package, `ui.command_palette` searches/configures caller-owned QAction
mappings. It imports no application feature modules. `persistence.session.SessionStore`
provides bounded, atomic, private JSON checkpoints without Qt; callers own record
schemas, live-instance locking, restoration and worker policy.


## Diff and merge review

`diff_bands.DiffEdit.set_diff()` maps patch-line metadata to Qt document blocks,
including embedded carriage returns and Unicode paragraph separators. Continuation
blocks retain the line's diff color and leave old/new numbers blank. Blocks without
metadata render without diff annotations, including during document changes.

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

Indentation guides use QTextLine cursor positions rather than rounded font metrics.
They are centered in the leading whitespace cell before each indent boundary and
painted only over the first visual row of a block, avoiding wrapped continuation
text. Tab stop distances use QFontMetricsF so font changes and zoom preserve
fractional glyph advances. The editor's public indentation settings are unchanged.

## Host-supplied change markers

The line-number gutter fits the current digit count and font. It reserves a small
change-marker lane and adds a folding lane only when foldable blocks exist;
fold-lane glyphs scale with the editor font. Number painting and fold hit testing
use separate lanes. Width shrinks again when line counts or fold ranges decrease.

`markers.line_changes(before, after)` returns immutable LineChange records with
zero-based half-open old/new line spans and add/modify/delete kinds. Deletions
anchor before `start`, including EOF. Hosts call `CodeEdit.set_line_changes(changes,
label)` to paint a separate eight-pixel lane left of folding and numbers; label is
the gutter tooltip. Empty changes clear markers. Painting respects visible blocks
and wrapping. Line-number visibility controls the whole gutter. Hosts own baseline
selection, background comparison, size limits, invalidation and shared-view fanout.
The widget performs no Git or filesystem operations.
Added lines use a clean Okabe–Ito blue-green vertical band; deleted
boundaries use orange-red horizontal marks, so shape also distinguishes them.
Unequal replacement blocks pair the common old/new span as modifications and
return surplus removed/added lines as separate delete/add records. Their old/new
spans partition the block, so hosts can review or restore each part independently.

`set_column_guide(column)` draws a dashed, palette-aware viewport ruler for
monospace columns. Zero (the shared default) disables it; valid values are 0–1000.
The ruler follows font metrics and horizontal scrolling, is copied when sharing
an editor document, and does not change text, wrapping or scroll extents.

Language choices and filename detection now come from `formats.code_syntax`,
shared with the native source input without importing Qt. The common Pygments
Blade grammar lives in `formats.code_blade`; the existing nested desktop import
continues to expose that same grammar. Qt's incremental block formatter remains
in this package; native text views apply UTF-16 spans from `formats.code_spans`.


`formats.code_language.LanguageSelection` supplies portable automatic/manual
selection for hosts that expose language controls. It is also used by native
CodeInput. The host owns choosing a language, applying it to SyntaxHighlighter,
folding/comment behavior, display captions and saving the selection. See the
[language API](../../formats/formats.md#editor-language-selection).
