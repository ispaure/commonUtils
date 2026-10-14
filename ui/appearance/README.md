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
- `status_line`: compact, muted, UI-font footers and native status-bar styling

`StatusLine(text='', parent=None)` matches File Browser's italic, muted footer.
It stays one line and elides visible text; `text()`, tooltip and accessible
description retain the complete message. `clear()` clears all three. Font changes
follow the shared UI role, not the content/reading/code font. Standalone labels
include 10-pixel horizontal and 6-pixel vertical padding; hosts with their own
footer row can override margins. Long messages cannot expand a workspace's height.
`style_status_bar(bar)` applies the same font/color to a QStatusBar without moving
its existing controls or changing timed-message behavior. Both require QApplication.
File Browser's `IndexStatusLabel` retains its public name as a specialized subclass
with outer padding supplied by its workspace row.

The shared font controller guards each widget while applying a role and callback.
FontChange events raised by `setFont` or callback formatting cannot recursively
reapply the same widget's role. This preserves component treatments such as
italic footers with application-wide styling enabled.

[Styling contracts](../styling.md) and [UI setup](../README.md).

Theme changes retain the existing Fusion engine and coalesce system notifications.
Resolved font roles are cached; repeated control polish does not rebind unchanged roles.
