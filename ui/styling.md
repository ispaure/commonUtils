# Shared styling

`ui/settings.ini [Styling]` declares 11 settings. Families and sizes use four roles:
`ui_font_*` (interface and dialogs), `browser_font_*`, `reading_font_*` (Markdown
and consumer book readers), and `code_font_*` (editors, diffs and Markdown code).
Each pair has `family_str` and `size_int`; blank families use the platform font,
with one shared monospace fallback for editors, diffs and Markdown code. Defaults
are 10 pt for UI/browser, 9 pt for code and Arial at 10 pt for reading. All four font sizes
allow 7–24 pt.
Sizes are reference points at 96 logical DPI: an 11 setting occupies about
15 logical pixels on every platform. `ui.appearance.typography.point_size(size)`
converts that setting to Qt points using its font DPI; `setting_size(font)` converts
back for zoom and persistence. This compensates for macOS's usual 72 font DPI
without overriding Qt's screen scaling. Families retain their native metrics,
so identical sizes do not guarantee identical glyph widths. Previews, Markdown
code, reading controls and editor zoom use the same convention. Saved values and
their 7–24 range remain unchanged; macOS text becomes larger at the same setting.
The smaller shipped defaults (10 for UI/browser/reading, 9 for code) retain the
previous macOS proportions across platforms. Existing personal overrides take
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
