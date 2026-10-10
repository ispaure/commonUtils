# features

Qt-independent feature declarations; browser bindings are created lazily.

Import from `commonUtils.features`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `resolve_type`, `ActionContext`, `FileType`, `FileTypeOverride`, `SelectionAction`, `FileActivation`, `BrowserExtension`, `Feature`

[Library overview](../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `resolve_type` | Resolve an optional 'package.module:Class' reference only when needed. |
| `FileTypeOverride` | Explicit subclass replacement, separate from extension-based FileType rules. |
| `SelectionAction` | handler(context) receives only accepted objects from the captured selection. |
| `FileActivation` | The first matching activation handles a double-clicked file. |
| `Feature` | One declaration for owned file types and per-window browser capabilities. |
