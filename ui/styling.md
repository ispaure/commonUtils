# Shared styling

`ui/settings.ini [Styling]` declares 11 settings. Families and sizes use four roles:
`ui_font_*` (interface and dialogs), `browser_font_*`, `reading_font_*` (Markdown
and consumer book readers), and `code_font_*` (editors, diffs and Markdown code).
Each pair has `family_str` and `size_int`; blank families use the platform font,
with one shared monospace fallback for editors, diffs and Markdown code. Defaults are 11 pt for UI/browser/code and 15 pt Georgia
for reading. UI/browser sizes allow 7–32 pt, reading 8–48, code 7–48.

`theme_mode` selects system/light/dark. `accent_color_str` accepts a QColor value.
`dark_tint_int` (0–20 percent) mixes the accent into neutral dark surfaces.
Selection text chooses black or white for contrast. `ui.theme.configured_colors`
returns effective colors; the existing base palette constants remain available.

Hosts call `apply_styling(app)` after QApplication/theme creation to opt into the
application/dialog font. `styling()` returns a controller; `bind_font(widget,
role, callback=None)` binds a live role without changing other host widgets.
A 500 ms timer rereads file timestamps and applies saved changes. `changed`
notifies consumers that own specialized rendering. Bindings use weak references;
text defaults preserve document modified flags. Markdown refreshes fenced and
inline code fonts along with reading fonts. Font changes do not save documents.

`styling().code_font.bind(editor)` connects a code editor's zoom signal to the
shared personal size; `set_size(size)` saves a sparse [Styling] override and updates
all bound code views. Hosts register paths using the layered configuration API.
For central settings navigation, a host may set
`app._commonutils_open_settings = callback(parent, category)`; Markdown's appearance
button then calls it with `commonutils`, and its zoom uses the shared personal
reading size. Without this callback Markdown retains a local reading-size popup.
Shared UI does not import consumer feature registries or windows.
