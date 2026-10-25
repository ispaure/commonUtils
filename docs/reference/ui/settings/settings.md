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
- `navigation`
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

Successful Save refreshes values, sparse override indicators and conflict snapshots
without rebuilding the form. Existing controls and font previews retain identity,
so the active tab, focus, selection and scroll stay in place. Parser-normalized
values are synchronized with signals blocked. Repeated saves use the latest file
snapshot; external changes still require Reload. Explicit Reload rebuilds controls
and rereads the schema. A write followed by a readback error reports that the write
succeeded but that Reload is required, rather than reporting an ordinary success.

## Category navigation

`navigation.SettingsNavigation(parent)` is a horizontal splitter exposing a
`sidebar` (`QTreeWidget`) and retained `stack` (`QStackedWidget`). Hosts populate
category items and connect their selection policy to the stack, supporting lazy
feature pages as well as static forms. The widget owns presentation, accessible
category naming and splitter proportions; it does not discover features or read,
write or apply configuration. Logistics settings and its build manager use this
same navigation shell with separate fields and persistence policies.
