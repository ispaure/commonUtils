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

`commonUtils.text_files` supplies Qt-independent BOM/encoding handling, text/binary
sniffing, normalized text snapshots and atomic conflict-checked byte writes. Use
explicit codecs for ambiguous legacy encodings and retain snapshots until save.
No existing File class is changed or automatically coupled to an editor.
