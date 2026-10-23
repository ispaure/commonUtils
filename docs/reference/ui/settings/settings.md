# Settings editor widgets

Typed INI editors, layered overrides, settings sections and font previews. Parsing, persistence and host-owned paths remain in configuration.

Import implementations from `commonUtils.ui.settings.<module>`.
Import widgets and helpers directly from these modules. Package imports do not
eagerly load their widgets. Former flat `commonUtils.ui.<module>` forwarding
modules have been removed; update imports and mock patch targets to this package.

## Modules

- `ini_editor`
- `layered_settings`
- `settings_sections`
- `font_preview`

[Configuration contracts](../../configuration/configuration.md) and [editor workflows](../../../user/components/components.md).
