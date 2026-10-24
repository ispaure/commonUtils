# Shared text and INI editors

These embedded editors edit a file chosen by their host application. The plain text
editor handles UTF-8 text; the INI editor adds section fields and an optional typed
settings convention. They are separate from a host's complete text-editor workspace.

## Edit, save and reload

Edit text and choose Save (or the platform Save shortcut). Changes are not written
until explicitly saved. Reload reads the disk copy and first offers a decision about
unsaved changes. A cooperating host also asks Save, Discard or Cancel before closing
an editor with changes; Cancel keeps it open.

Files are saved by staging and atomic replacement. If the file changed on disk since
loading, saving is refused and an error remains visible. Preserve text you need before
reloading the external version. A failed save retains your edits. An unreadable or
non-UTF-8 file opens with an error rather than silently replacing bytes. BOMs and the
editor's detected newline style are retained; this is not a general encoding converter.

## Edit INI fields or source

Use section tabs for individual values, or Source to inspect the complete INI.
Ordinary INI values are text, even when their names resemble types. If the host opts
into typed keys, booleans become checkboxes and choice fields can become dropdowns;
numbers and lists are validated before saving. Unrecognized suffixes stay text.

The mouse wheel scrolls settings pages without changing values under the pointer,
even when a field has focus. This includes numeric, date/time and dropdown fields,
sliders and dials. Use typing, keyboard arrows or clicks to change values. Open a
dropdown to scroll its available choices.

Invalid typed fields block Save and switching to Source until corrected or discarded.
Malformed INI files open in Source for repair. Comments and unrelated formatting are
preserved where a field can be patched unambiguously. Ambiguous formatting is reported
instead of silently rewriting unrelated settings. Saving notifies the host, which
chooses when to apply the changed configuration.

For typed lists, use JSON syntax such as `["one", "two"]` or `[1, 2]`. Dates and other
application rules are not automatically inferred from plain text fields. A successful
type check does not prove a path exists or that a setting is meaningful to the host.

## Shared reading preferences

Some hosts expose `ui/settings.ini` through this editor. Page-turning components that
adopt the shared wheel preferences read saved changes on their next event:

| Wheel preference | Behavior |
| --- | --- |
| `immediate_notches` | True turns one page per snapped-wheel event without a cooldown; false applies smooth thresholds/cooldown to all wheels. |
| `sensitivity` | Higher values need less smooth scrolling to turn a page (range 1–100). This does not change ordinary list scrolling. |
| `cooldown_ms` | Minimum interval between smooth page turns (0–2000 ms); larger values reduce bursts. Immediate notches bypass it. |

The checked-in file sets true, 100 and 30 ms. Missing/invalid values fall back to true,
20 and 250 ms. Loading, modifiers and modal dialogs can still block a page turn.
Only components using page navigation adopt these preferences; a plain text document's
continuous scroll is different. [Browser preferences](../file_browser/file_browser.md#settings-and-their-effects)
have their own guide.

[Configuration integration](../../reference/configuration/configuration.md) · [All shared guides](../../overview.md#shared-component-user-guides)

## Menus in hosted windows

When an application hosts readers or editors in workspace tabs, macOS menus follow
its selected document or destination as focus changes. Detached windows follow
their own selected tab. Menu updates preserve the document's commands and keyboard
focus; opening a menu is not required to refresh the context.
Creating a document from a tab's + menu uses the same menu switching behavior as
opening one through the host's document launcher.

## Confined editor tab moves

In applications using confined editor groups, drag a tab onto another group's
header to combine/reorder tabs, its center to combine groups, or its left/right
edge to split or reposition a column. The preview follows the current target;
releasing completes the move even when the pointer crosses into another editor.
Escape or releasing outside the editor area cancels. Hiding the source or
switching windows during a gesture also clears the preview. The host controls
which moves are allowed and keeps ownership of files and unsaved edits.

## macOS menu placement

In Settings → commonUtils, open `ui/settings.ini` and set
`[Menus] macos_native_bool`. The default `true` places menus in the macOS system
menu bar. Set it to `false` to use the same in-window placement as Windows/Linux.
Save to apply within half a second to existing and new editors, readers and tools.
Attached views show their own menus; detached windows show the active view’s
menus in their header. Commands and shortcuts stay the same. Windows/Linux
always use in-window menus. Missing or invalid values use `true`.

Click a menu title once, then move the pointer across neighboring titles to
browse their options without another click. Press Escape to dismiss the menu.

## Shared appearance

Hosts can expose software defaults and personal settings using the shared settings
editor. Personal fields show Inherited or Override; **↶** removes an override, then
Save applies it. Software mode edits the defaults INI and ↶ reverts an unsaved
field. Font sizes range from 7 to 24 pt. Appearance has four font roles: interface/dialogs, browsers, reading, code.
Ordinary buttons, including Save and Reload, follow the interface font. Buttons
inside browser panels follow the browser font; sample buttons use the preview font.
Font dropdowns display each family name in its own typeface so you can preview
fonts while browsing. EPUB and Markdown use Arial at 10 pt by default, a neutral
sans serif for books and technical documentation; personal
font choices override that default. Choose Automatic to use the role's fallback font, or type
a font family name directly. The selected field also uses the chosen typeface.
Samples underneath show interface controls, browser entries, reading text or code
using the pending family and size. Selecting a font, changing its size or resetting
it updates the sample immediately; the application changes only after Save.
The code list contains only monospace fonts (equal character widths). Automatic
uses the platform's monospace fallback; typed code font names must be monospace too.
On Windows, the lists exclude legacy bitmap/vector fonts such as Terminal and
Fixedsys. Choose a scalable outline font or Automatic. Unsupported typed names
use a safe preview and show an error on Save; old saved choices use a fallback.
Markdown uses the reading font for prose and the code font for source/code blocks.
Accent and dark surface tint update the theme. In a host with central settings,
Markdown's appearance button opens that host window; standalone hosts retain a
local reading-size popup.

New Tab (+) appears in the active tab strip or the view toolbar when a single-tab
header is collapsed. Hidden or retired headers do not display extra + buttons.

The Menus settings include **Launch with sidebar**, enabled by default, for hosts
that support sidebar navigation on their launch screen. Hosts apply the choice
when opening a workspace.

Saving a layered settings form keeps the current tab, scroll position and existing
controls, including font previews. Override indicators update immediately. Reload
rereads the files and rebuilds the form; external changes must be reloaded before
saving over them.

## Password visibility

Password and token controls start hidden. Use the eye button to show or hide the
current value. Clearing the field hides it again. The application decides when
credentials are submitted, retained or cleared.
