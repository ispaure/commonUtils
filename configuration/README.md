# INI configuration and settings editors

[Shared editor user guide](../ui/user_docs/README.md) · [Developer API map](../docs/developer/public-apis.md)

Use `INIFile` for ordinary INI documents. Add the typed-key schema when you want
consistent value validation, and the Qt editor when you want people to edit those
settings visually. Each layer works independently.

| Layer | Import | Responsibility |
| --- | --- | --- |
| INI document | `commonUtils.formats.iniType.INIFile` | String values, parsing, formatting preservation and safe saves |
| Optional schema | `commonUtils.configuration.ini_schema` | Typed suffixes, list parsing and dropdown choices |
| Visual editor | `commonUtils.ui.settings.ini_editor.INISettingsEditor` | Section tabs, key rows, validation and explicit saving |

The document and schema have no GUI dependency. The editor requires PySide6 and
an existing `QApplication`. These modules contain no application-specific paths,
feature names or settings. Applications own defaults, domain rules and what
happens after a setting changes. The standalone configuration helpers live in `commonUtils.configuration.legacy`.

## Read and update an ordinary INI

```python
from pathlib import Path
from commonUtils.formats.iniType import INIFile

config = INIFile(Path("config.ini")).read()
name = config.get("General", "name", fallback="")
config.set("General", "name", "Example")
config.save()
```

Values stay strings, even when a key ends with `_int` or `_bool`. Parsing preserves
key case and disables interpolation, so percent signs remain literal. Duplicate
keys/sections and malformed files raise standard ConfigParser errors.

Field updates retain comments, unrelated formatting, multiline values, UTF-8 BOMs
and line endings. Saves are atomic and refuse a file changed since `read()`.
Ambiguous formatting raises an error rather than changing unrelated values;
the editor's Source tab lets you correct it. Coordinate concurrent writers in
your application: the conflict check is not a cross-process lock.

See [INIFile details](../formats/README.md#initypepy) for the full document API.

## Opt into typed keys

The optional convention puts a type at the end of each key:

```ini
[Display]
title_str = My browser
preview_bool = true
max_items_int = 5000
scale_float = 1.25
view_mode = tiles
view_choices_list-str = ["tiles", "list", "columns"]
```

| Suffix | Expected value |
| --- | --- |
| `_str` | Text |
| `_int` | Whole number |
| `_float` | Finite number |
| `_bool` | `true` / `false`; also accepts yes/no, on/off and 1/0 |
| `_list-str` | JSON string list, such as `["one", "two"]` |
| `_list-int` | JSON integer list, such as `[1, 2]` |
| `_list-float` | JSON number list, such as `[1, 2.5]`; numbers must be finite |
| `_list-bool` | JSON boolean list, such as `[true, false]` |
| `_mode` | Selected string; use `<name>_choices_list-str` to define choices |

A mode stores one selected value. Its companion choices key defines the dropdown;
`view_mode` pairs with `view_choices_list-str`. Without choices, it uses a text
field. Empty choice lists permit no selected value, so they cannot be saved as a
valid mode configuration. String lists also accept `[one,two]` for simple names;
use JSON quotes for strings containing commas. Numeric lists do not coerce strings
or booleans to numbers. Keys without a recognized suffix remain ordinary text.

Validate a document or retrieve a typed value without importing Qt:

```python
from commonUtils.configuration.ini_schema import (
    key_type, parse_value, validate_values,
)

parser = INIFile.parse(config.text)
validate_values(parser)  # Raises ValueError with the section/key on failure.
base, kind = key_type("max_items_int")  # ("max_items", "int")
count = parse_value(kind, parser.get("Display", "max_items_int"))
```

`parse_value()` returns Python strings, integers, floats, booleans or lists.
`string_list()` parses string lists. `mode_choices(key, section_values)` finds and
parses a mode's companion choices; pass its result to `parse_value(..., choices=...)`
when reading a mode individually. `validate_values()` checks all sections,
including DEFAULT values inherited by other sections.

The schema checks types and choices. An application can additionally require a
positive count, an existing path or another domain constraint. Do that before
using values; an editor save does not prove an application's domain rules hold.

## Embed the editor

```python
from commonUtils.ui import pyside as qt
from commonUtils.ui.settings.ini_editor import INISettingsEditor

app = qt.QApplication.instance() or qt.QApplication([])
editor = INISettingsEditor("config.ini", typed_keys=True)
editor.saved.connect(lambda path: print("Saved:", path))
editor.resize(800, 600)
editor.show()
app.exec()
```

**Typed keys are off by default.** `INISettingsEditor(path)` shows plain string
rows, even for keys ending in `_int`. Pass `typed_keys=True` to enable the schema,
boolean checkboxes and mode dropdowns. Numeric and list values use text fields
with validation, allowing large integers without a widget's 32-bit limit.

Sections appear as tabs; each key has a row. Multiline values use a taller field.
The Source tab exposes the original INI text. Malformed INIs open there so they
can be repaired. Invalid typed fields block saving and switching to Source until
corrected or discarded. Changes are written only with Save; `saved(path)` then
notifies the application, which decides whether to reload settings.

The editor inherits `TextFileEditor`'s `save()`, `reload()`, `is_modified` and
`can_close()` lifecycle. Call `can_close()` before removing it or closing its host
to offer Save, Discard or Cancel. File switching should retain editor instances
if you want pending edits preserved. Each editor refuses external disk changes.
For custom save rules, subclass the editor and validate before `super().save()`.

## Settings adoption

Adopt typed keys gradually. Changing a key name requires updating its consumers;
plan how existing saved values will be read. Neither the
schema nor editor automatically renames existing keys or rewrites legacy files.

Import shared settings from `commonUtils.configuration.settings`. Applications
choose their own defaults and supply a custom settings path when needed.

## Shared navigation settings

`commonUtils.configuration.settings.settings_path()` locates `ui/settings.ini` beside the browser
package. Applications choose where to expose this file. Components using shared page-wheel
navigation read saved changes on the next wheel event.
`get_setting(section, key, default, minimum=None, maximum=None)` reads bool, int,
float or string values using the default's type (bounds are keyword arguments).
`get_wheel_navigation_settings()` returns immutable validated wheel preferences.
Both accept a keyword `path` override for other hosts/tests. Missing, unreadable,
malformed or invalid settings use defaults; reads never rewrite the INI. File
identity timestamps cache parsing and invalidate it after edits.

The `[WheelNavigation]` fallback defaults are `immediate_notches=true`, `sensitivity=20`
(range 1–100), and `cooldown_ms=250` (range 0–2000). Each vertical angle-only wheel
event with no scroll phase turns one page regardless of delta magnitude. Smooth
pixel/phase events accumulate to 60 pixels or 120 angle units divided by sensitivity,
with a cooldown to avoid bursts. Disable immediate notches to apply the smooth
threshold and cooldown to all wheels. Loading, modifiers and modal dialogs still
block navigation. These preferences affect discrete page navigation, not ordinary
file-browser list scrolling.


The checked-in `ui/settings.ini` overrides sensitivity to 100 and cooldown to
30 ms. These saved values differ from missing/invalid-value fallbacks. Browser
preview, storage animation and index preferences are explained in the
[File Browser settings guide](../ui/file_browser/user_docs/README.md#settings-and-their-effects).

## Shared menu placement

`[Menus] macos_native_bool=true` in `ui/settings.ini` enables the macOS system
menu bar. False uses desktop in-window placement; other platforms ignore the
flag. Missing/invalid values default to true. The shared application initializer,
reader menus, Markdown windows and workspace menu router install
`commonUtils.ui.menu_policy.install_menu_policy(app=None)` once per application.
Hosts creating their own QApplication can call it directly for all their menus.
It has no import-time effects and polls saved settings every 500 ms, updating
existing menu bars and routing contexts without recreating actions. New menu
bars inherit the application policy. Workspace source bars stay non-native to
avoid publishing duplicate commands.

Workspace menu publication owns its native-bar rebind events. The application
policy ignores those events so publication settles instead of repeatedly
rebinding menus during pointer tracking.

## Software defaults and sparse personal overrides

`configuration.layered.register_settings(defaults, personal)` associates a
repository INI with a host-owned personal INI. Reads never create files.
`get_setting` reads registered overrides with typed validation and falls back to
the software value when a personal value is invalid. `effective_settings` provides
a ConfigParser overlay for legacy non-typed readers. A malformed personal file is
ignored for reads and preserved; editors refuse to overwrite malformed files.

`LayeredSettings(defaults, personal)` exposes `values(scope)`, `overrides()` and
`save(changes, scope='personal', expected=None)`. Scope `application` edits the
software INI; `personal` edits only overrides. Changes map `(section, key)` to
strings. A `None` removes an explicit personal field and its continuation lines;
it is forbidden for software-default fields. `expected=(original_bytes,)` adds
an editor snapshot check. Atomic saves retain unrelated fields, comments, BOM,
line endings and permissions and reject concurrent edits. Unsafe removal layouts
raise rather than corrupting the file. Defaults and personal paths must differ.

`shared_settings()` uses registered shared UI paths, or a platform-standard
persistent commonUtils directory when the host has not supplied its own mapping.
Hosts own discovery, migrations and path policy; shared code does not discover
application features. `ui.settings.layered_settings.LayeredSettingsEditor` provides explicit
Save/Reload, indicators and per-field ↶ reset for a declared schema. It accepts a
scope, optional section filter, labels and host validator for domain constraints.
Dirty editors compare both layers before saving. Choice metadata supplies mode
dropdowns rather than appearing as a user preference. Undeclared personal session
fields are retained on disk but omitted from the software settings form.

Mobile hosts must register an explicit personal settings path before calling
`layered.shared_settings()`. Automatic desktop paths are rejected on iOS/Android;
registration and reads do not create a settings file or grant sandbox access.

## Migration completion

`configuration.migrations.MigrationLedger(path)` keeps host-supplied versioned
migration IDs outside resettable preferences. `state(id)` reads without creating
files; `run(id, callback, already_applied=False)` returns whether work ran.
Completed migrations are skipped. `already_applied=True` adopts a legacy marker
only when there is no ledger entry. Pending is saved before invoking the callback,
and completion only after it succeeds, so partial failures retry even if they
created a destination. Callbacks must be idempotent and preserve newer overrides.
`complete(*ids)` lets a host deliberately suppress legacy imports during reset.

The caller owns paths, IDs, legacy detection, transforms, error presentation and
writer coordination. Metadata uses atomic, conflict-checked INI saves; malformed
files/states propagate errors rather than silently re-running imports. This is
not a multi-file transaction or a process lock. Keep the ledger outside any
directory erased by reset, and serialize concurrent migration calls in the host.
