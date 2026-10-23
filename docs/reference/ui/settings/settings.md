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

## Layered field construction

`LayeredSettingsEditor._build` retains section filtering, tab replacement and the
rebuild guard. `_field_control` selects and binds one schema control; its returned
font-family cache is local to that rebuild and populated only for a font selector.
`_add_field_row` installs accessibility labels, color actions, reset/override state
and optional font previews. Signal callbacks capture the field identity and any
required control before the loop advances. Parsing, pending sparse overrides,
conflict checks and explicit-save publication remain in their existing owners.

Configuration, styling, wheel-policy and mixed-field tests cover inheritance,
invalid/unknown values, preview isolation, independent section callbacks, reset,
concurrent edits and no-op saves. Construction does not persist or apply settings.

[Configuration contracts](../../configuration/configuration.md) and [editor workflows](../../../user/components/components.md).
