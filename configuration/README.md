# INI configuration and settings editors

Use `INIFile` for ordinary INI documents. Add the typed-key schema when you want
consistent value validation, and the Qt editor when you want people to edit those
settings visually. Each layer works independently.

| Layer | Import | Responsibility |
| --- | --- | --- |
| INI document | `commonUtils.fileTypes.iniType.INIFile` | String values, parsing, formatting preservation and safe saves |
| Optional schema | `commonUtils.configuration.ini_schema` | Typed suffixes, list parsing and dropdown choices |
| Visual editor | `commonUtils.ui.ini_editor.INISettingsEditor` | Section tabs, key rows, validation and explicit saving |

The document and schema have no GUI dependency. The editor requires PySide6 and
an existing `QApplication`. These modules contain no application-specific paths,
feature names or settings. Applications own defaults, domain rules and what
happens after a setting changes. The existing `configUtils` API stays available.

## Read and update an ordinary INI

```python
from pathlib import Path
from commonUtils.fileTypes.iniType import INIFile

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

See [INIFile details](../fileTypes/README.md#initypepy) for the full document API.

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
from commonUtils.ui.ini_editor import INISettingsEditor

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

## Migration and compatibility

Adopt typed keys gradually. Changing a key name requires updating its consumers;
keep fallback reads for the old name where compatibility matters. Neither the
schema nor editor automatically renames existing keys or rewrites legacy files.

Applications can retain compatibility imports or a small wrapper to preserve
their previous defaults while migrating. New consumers should import the
commonUtils modules directly.

`settings.py` owns the historical `settings` implementation; its compatibility
package preserves existing consumers.
