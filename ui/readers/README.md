# Shared reader controls

Reader menus, fullscreen controls, read-aloud presentation and wheel navigation shared by document readers.

Import implementations from `commonUtils.ui.readers.<module>`.
Import widgets and helpers directly from these modules. Package imports do not
eagerly load their widgets. Former flat `commonUtils.ui.<module>` forwarding
modules have been removed; update imports and mock patch targets to this package.

## Modules

- `reader_chrome`
- `reader_menus`
- `read_aloud`
- `page_wheel`

[Shared reader workflows](../user_docs/README.md) and [Markdown](../markdown/README.md).
