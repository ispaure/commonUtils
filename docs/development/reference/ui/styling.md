# Shared styling

## Panel status footers

`ui.appearance.status_line.StatusLine` is the shared single-line status label.
It uses the UI font, muted italic text and fixed vertical sizing. Long messages
are elided; `text()`, the tooltip and accessible description retain the full message.
Newlines display as separators and do not increase the footer height.

For messages with trailing controls, use `StatusFooter(text='', parent=None)`
from the same module. Its `message` is a `StatusLine`; append progress meters,
Cancel buttons or other controls with `footer.layout().addWidget(control)`.
Place the footer after the panel content in its vertical layout. It keeps its
natural row height as the panel grows, leaving the extra space to the content.
Plain message footers can use `StatusLine` directly. Native `QStatusBar` hosts
use `style_status_bar(bar)` to share typography while preserving timed messages
and permanent controls.

`ui.tasks.operation_progress.OperationProgress` uses `StatusFooter` for its
message, bounded progress meter and Cancel button. See
[operation progress](operation_progress.md) for worker and cancellation ownership.

## Typography and themes

`ui/settings.ini [Styling]` declares 11 settings. Families and sizes use four roles:
`ui_font_*` (interface and dialogs), `browser_font_*`, `reading_font_*` (Markdown
and consumer book readers), and `code_font_*` (editors and diffs; the family also
applies to Markdown code).
Each pair has `family_str` and `size_int`; blank families use the platform font,
with one shared monospace fallback for editors, diffs and Markdown code. Defaults
are 10 pt for UI/browser, 9 pt for code editors and Arial at 12 pt for reading. All four font sizes
allow 7–24 pt.
Sizes are reference points at 96 logical DPI: an 11 setting occupies about
15 logical pixels on every platform. `ui.appearance.typography.point_size(size)`
converts that setting to Qt points using its font DPI; `setting_size(font)` converts
back for zoom and persistence. This compensates for macOS's usual 72 font DPI
without overriding Qt's screen scaling. Families retain their native metrics,
so identical sizes do not guarantee identical glyph widths. Previews, Markdown
code, reading controls and editor zoom use the same convention. Saved values and
their 7–24 range remain unchanged; macOS text becomes larger at the same setting.
Markdown inline code and fenced blocks use the surrounding document's reading
size, including local reading zoom. They use the shared monospace family but
ignore the code editor size. Source Markdown editing uses the code role throughout. Existing personal overrides take
precedence and are never rewritten to the new defaults.
Code families must be installed fixed-pitch fonts, or blank for the monospace
fallback. The layered editor filters its code family list accordingly and validates
typed names on Save. Existing unavailable or proportional saved code families fall
back at runtime without rewriting configuration.

On Windows, all four family roles require smoothly scalable outline fonts.
The dropdown excludes legacy GDI bitmap/vector families (including Terminal,
Fixedsys and MS Sans Serif) before assigning preview fonts, and filters other
non-scalable families using QFontDatabase metadata. Typed unsupported names are
rejected on Save and use a fallback for local previews. Saved unsupported choices
fall through to software defaults or the role fallback without rewriting the INI.
Other platforms retain their existing family selection behavior.

Preference reads before GUI startup reject known Windows legacy names but defer
font-database metadata checks. Qt requires a QGuiApplication for those queries;
the styling controller performs full family validation after GUI construction.

The layered editor renders font names and its selected editable field in the
chosen family. Local sample widgets preview pending families/sizes and resets;
they never bind to the live role controller or save preview changes. Automatic
browser/reading previews inherit the pending interface family. Samples rebuild on
Reload/Save and remain separate from application/document state.

`theme_mode` selects system/light/dark. `accent_color_str` accepts a QColor value.
`dark_tint_int` (0–20 percent, default 6) mixes the accent into neutral dark surfaces.
Selection text chooses black or white for contrast. `ui.appearance.theme.configured_colors`
returns effective colors; the existing base palette constants remain available.

Hosts call `apply_styling(app)` after QApplication/theme creation to opt into the
application/dialog font. `styling()` returns a controller; `bind_font(widget,
role, callback=None)` binds a live role without changing other host widgets.
Application opt-in also binds existing buttons/menus/menu bars and those polished
or shown later. They use the interface role unless a containing component is bound
to another role (for example browser controls). Explicit bindings and local font
preview samples take precedence. Legacy `pyside.set_font` controls use that live role
in opted-in hosts. Theme refresh runs before applying the application font and
updating role bindings, preserving saved typography through repolishing.
The shared settings monitor checks for external changes every 500 ms; saved
changes are delivered through GUI-thread subscriptions. `changed`
notifies consumers that own specialized rendering. Bindings use weak references;
text defaults preserve document modified flags. Markdown refreshes fenced and
inline code fonts along with reading fonts. Font changes do not save documents. Formatted Markdown applies code fonts through
layout highlighting, so changing appearance does not add editing undo commands.

`styling().code_font.bind(editor)` connects a code editor's zoom signal to the
shared personal size; `set_size(size)` saves a sparse [Styling] override and updates
all bound code views. Hosts register paths using the layered configuration API.
For central settings navigation, a host may set
`app._commonutils_open_settings = callback(parent, category)`; Markdown's appearance
button then calls it with `commonutils`, and its zoom uses the shared personal
reading size. Without this callback Markdown retains a local reading-size popup.
Shared UI does not import consumer feature registries or windows.

Theme transitions reuse the Fusion style engine, coalesce system-color notifications,
and skip unchanged palettes/stylesheets. Font roles cache their resolved fonts and
already-bound controls are not rebound during polish/show events. Syntax highlighting
skips palette notifications that retain its effective token style. These changes
avoid repeated font/layout work while preserving document text, undo and saved sizes.

Accent and dark-surface tint changes use palette brushes in the application
stylesheet. When its text is unchanged, the theme controller unpolishes/polishes
the application style to invalidate cached QSS brushes, rather than resetting the
stylesheet and repolishing every widget. Light/dark transitions can still replace
the stylesheet because muted tab/disabled colors differ. Rendered-pixel tests
check that existing fields, checked buttons and progress bars adopt successive
accent/surface changes; checking palette values alone misses stale QSS brushes.

Saved styling reloads update only changed font roles. Automatic browser/reading
families also follow interface font changes, and reading callbacks run for code
family changes because documents contain code spans. Accent-only reloads retain
font caches and skip font-binding callbacks. The broad `changed` signal still
fires for specialized color/rendering consumers.
