# Shared code editing and review

These editing controls can be embedded in different applications. The host chooses
which commands, preferences, split views and review dialogs are exposed, and owns
opening/saving files, tabs and recovery. This guide covers shared editing behavior.

## Edit efficiently

The editor provides line numbers, indentation, line commands and font zoom. Automatic
indentation continues indentation when enabled. Optional automatic pairing inserts
matching delimiters; it is off by default in the bare shared editor. Indentation width
and tabs-versus-spaces are chosen by the host. Line transformations can sort, remove
duplicate lines, trim trailing spaces or change indentation; they are undoable.

Line-number gutters follow the editor font and resize when the font or line count
changes, including when the surrounding window keeps its size.

Alt-click adds cursors; Alt+Shift-drag selects a rectangular column region. Typing
changes multiple selections as one undo operation. Pasting the same number of lines
as cursors distributes them. There is no virtual-space padding beyond line ends,
and outside document changes can clear extra cursors. Folding hides structural
regions without deleting their content. Large/complex inputs have bounded analysis.

Syntax highlighting is optional. Without a lexer, or for very large documents or
long lines, text can remain uncolored while still editable. Coloring is not validation.

## Find and replace

When the host exposes the shared search panel, bind your work to the active document.
Literal/regular-expression searches run in the background; stale results are discarded
after changes. Replace All groups its changes into one undo step. Regular-expression
replacement supports numeric and named capture references. Patterns/match counts are
bounded, so a refused search does not mean the document cannot be edited.

If split views are available, they show the same document with independent cursor
navigation. An edit in one appears in the other; read-only state and folds are shared.
A split is not a second file copy.

## Compare and merge

A diff dialog can show side-by-side or unified changes with linked scrolling and
change bands. Applying a change is available only when the application provides
that action; it changes the host buffer according to the host's policy, not necessarily
the file on disk. Stale comparisons may need to be refreshed before applying.

In a three-way merge, inspect the left/right sources and editable result. Resolve a
change with **Left**, **Right**, **Both** (left then right), **Keep Base**, or a manual
edit followed by marking it resolved. The ancestor can be shown separately. Apply
becomes available once every change is resolved. Cancel discards the review session
without invoking the application's Apply action. Save the resulting document using
the host's normal workflow.

Blue marks modifications, green additions, gray deletions and red unresolved conflicts;
colors adapt to the palette. Large comparisons are bounded: diff and merge limits are
1,048,576 Python characters and 5,000 lines per side/input/result. The diff UI calls
its character limit “1 MiB”; it is not an encoded-byte measurement. These limits do not establish the host's ordinary file-opening limit.

## Troubleshooting

A disabled command may reflect read-only state, no suitable selection, an unresolved
merge, a stale buffer or a size limit. If a feature is absent entirely, the host may
not expose it. JSON/XML formatting is deliberately conservative and bounded; XML
with mixed content, CDATA or preserved whitespace can be refused rather than altered.

[Developer integration](../README.md) · [All shared guides](../../../README.md#shared-component-user-guides)

PHP files highlight embedded HTML. Laravel `.blade.php` files are detected before
ordinary PHP and highlight Blade directives and single-line interpolations using
the shared PHP/HTML grammars. Python stub (`.pyi`) files use Python highlighting.
Multiline Blade template expressions have limited highlighting.
