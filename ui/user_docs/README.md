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
continuous scroll is different. [Browser preferences](../file_browser/user_docs/README.md#settings-and-their-effects)
have their own guide.

[Configuration integration](../../configuration/README.md) · [All shared guides](../../README.md#shared-component-user-guides)
