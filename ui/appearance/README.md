# Shared UI appearance

Opt-in themes, live font styling and palette-aware painted icons.

Import implementations from `commonUtils.ui.appearance.<module>`.
Import widgets and helpers directly from these modules. Package imports do not
eagerly load their widgets. Former flat `commonUtils.ui.<module>` forwarding
modules have been removed; update imports and mock patch targets to this package.

## Modules

- `theme`
- `styling`
- `icons`

[Styling contracts](../styling.md) and [UI setup](../README.md).
