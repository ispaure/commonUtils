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

## Speech presentation and highlights

`ReadAloud` uses a percent slider (50–200%, 25% detents), a sleep timer with an
icon reset and bold countdown, and backward/play/forward/stop controls. Timer
elapsed time follows a monotonic deadline and freezes in paused/stopped states.
`positionChanged(-1, -1)` retires speech-owned highlights before skip requeue so
consumers can clear mirrored panes. The next word emits its replacement range.
Search and other untagged extra selections survive cleanup. See the
[read-aloud workflow](../markdown/user_docs/README.md#read-aloud).
