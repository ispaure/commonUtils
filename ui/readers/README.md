# Shared reader controls

Reader menus, fullscreen controls, read-aloud presentation and wheel navigation shared by document readers.

Import implementations from `commonUtils.ui.readers.<module>`.
The former `commonUtils.ui.<module>` paths remain compatibility aliases to the
same module objects, including their registries and patch targets. Package imports
do not eagerly load their widgets.

## Modules

- `reader_chrome`
- `reader_menus`
- `read_aloud`
- `page_wheel`

[Shared reader workflows](../user_docs/README.md) and [Markdown](../markdown/README.md).
