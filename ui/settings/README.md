# Settings editor widgets

Typed INI editors, layered overrides, settings sections and font previews. Parsing, persistence and host-owned paths remain in configuration.

Import implementations from `commonUtils.ui.settings.<module>`.
The former `commonUtils.ui.<module>` paths remain compatibility aliases to the
same module objects, including their registries and patch targets. Package imports
do not eagerly load their widgets.

## Modules

- `ini_editor`
- `layered_settings`
- `settings_sections`
- `font_preview`

[Configuration contracts](../../configuration/README.md) and [editor workflows](../user_docs/README.md).
