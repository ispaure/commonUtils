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
- `formatting_glyphs`: shared vector geometry and inline SVG, without GUI imports
- `formatting_icons`: palette-aware Qt adapter for the same geometry
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

## Formatting icons

`formatting_glyphs.py` owns the 24-point vector paths shared by Qt Markdown
controls and native WebView editors. `formatting_svg()` emits inline vectors
using the control's current color; the containing button supplies its accessible
name and tooltip. `formatting_icons.FormattingIcon` paints those same paths
through the palette-aware `set_painted_icon()` adapter. Keep geometry in the
shared module so desktop and mobile cannot drift into different icon sets.

## Portable color calculations

`ui.appearance.colors` provides `argb(hex_color)`, `contrast_ratio(first, second)`
and `readable_accent(accent, foreground, background)`. Integer channels accept
signed Android ARGB values. Accent blending moves toward the supplied foreground
until reaching 4.5:1 contrast or falling back to that foreground. These calculations
do not import Qt or Toga. Native painting and role providers are documented in the
[native surface guide](../native/README.md#surface-appearance-primitives).
