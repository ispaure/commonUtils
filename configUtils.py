# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS


"""
Functions to read through a (.ini) file.
"""

from typing import *
from pathlib import Path
import configparser

# Common utilities
from . import fileUtils
from .debugUtils import *


# ----------------------------------------------------------------------------------------------------------------------
# DEBUG

show_verbose = False


# ----------------------------------------------------------------------------------------------------------------------
# CODE


def config_section_map(
    cfg_file_path: Union[str, Path],
    section: str,
    variable: str,
    *,
    allow_duplicates: bool = False,
    fallback_to_bypass: bool = False,
    case_sensitive_keys: bool = False,
    strip_value: bool = True,
) -> Optional[str]:
    """
    Retrieve a value from a section of a config (.ini) file.

    Behavior:
    - Strict parser by default (will raise on duplicates unless allow_duplicates=True).
    - Interpolation disabled (safer; avoids '%' surprises).
    - UTF-8 with BOM supported via 'utf-8-sig'.

    Options:
    - allow_duplicates: if True, allows duplicate sections/keys (last one wins).
    - fallback_to_bypass: if True, if ConfigParser can't read the file, do a simple line-scan fallback.
    - case_sensitive_keys: if True, preserves key case (ConfigParser default lowercases keys).
    - strip_value: if True, strips whitespace from returned value.

    Returns:
        The value (str) if found, else None.
    """
    tool_name = "config_section_map"
    path = Path(cfg_file_path)

    # Decide key normalization
    lookup_key = variable if case_sensitive_keys else variable.lower()

    def _post(val: Optional[str]) -> Optional[str]:
        if val is None:
            return None
        return val.strip() if strip_value else val

    # ---- Normal parsing route ----
    config = configparser.ConfigParser(
        interpolation=None,
        strict=not allow_duplicates,
    )
    if case_sensitive_keys:
        config.optionxform = str  # preserve original key case

    try:
        with path.open("r", encoding="utf-8-sig") as f:
            config.read_file(f)
    except Exception as e:
        if not fallback_to_bypass:
            # During refactors this is usually preferable: fail loudly.
            raise
        # Fall back to bypass scan
        log(Severity.ERROR, tool_name, f"ConfigParser failed on '{path}': {e}. Falling back to bypass scan.")
        return _post(_bypass_scan_ini(path, section, lookup_key, case_sensitive_keys=case_sensitive_keys))

    # Section missing
    if not config.has_section(section):
        return None

    # Option missing (note: if case_sensitive_keys=False, ConfigParser lowercased keys)
    if not config.has_option(section, lookup_key):
        return None

    try:
        return _post(config.get(section, lookup_key))
    except Exception as e:
        # If value retrieval fails for some reason, mirror the same fallback behavior
        if fallback_to_bypass:
            log(Severity.ERROR, tool_name, f"Error getting '{lookup_key}' from [{section}] in '{path}': {e}. "
                                          f"Falling back to bypass scan.")
            return _post(_bypass_scan_ini(path, section, lookup_key, case_sensitive_keys=case_sensitive_keys))
        raise


def _bypass_scan_ini(
    cfg_file_path: Union[str, Path],
    section: str,
    variable: str,
    *,
    case_sensitive_keys: bool = False,
) -> Optional[str]:
    """
    Very tolerant .ini scanner:
    - Finds [section] blocks
    - Accepts 'k=v' or 'k = v'
    - Strips blank lines and comments (# or ;)
    - Stops when next [section] starts

    Does NOT support multiline values.
    """
    path = Path(cfg_file_path)

    # Prefer your existing fileUtils if you want; otherwise read directly.
    try:
        txt = fileUtils.TXTFile(path)
        txt.import_line_lst()
        lines = txt.line_lst
    except Exception:
        # Fallback read
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()

    target_section = f"[{section}]"
    in_section = False

    for raw in lines:
        line = raw.strip()

        if not line or line.startswith(("#", ";")):
            continue

        # New section header
        if line.startswith("[") and line.endswith("]"):
            in_section = (line == target_section)
            continue

        if not in_section:
            continue

        # Remove inline comments (simple heuristic)
        for c in (";", "#"):
            if c in line:
                line = line.split(c, 1)[0].strip()

        if "=" not in line:
            continue

        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()

        if not case_sensitive_keys:
            k = k.lower()
            var_cmp = variable.lower()
        else:
            var_cmp = variable

        if k == var_cmp:
            return v

    return None


def config_add_variable(cfg_file_path: Union[str, Path], section: str, variable: str, value: str):
    """
    Expects variable to not be there already.
    Adds a variable to a config file and sets its value. If required, add its section.

    Keeps file formatting reasonably:
    - Tries to match existing '=' spacing style if detectable, else uses ' = '.
    - If adding a new section, inserts a blank line before it (if needed).
    """
    path = Path(cfg_file_path)

    lines_lst = fileUtils.read_file(path)
    # Normalize to "no trailing newline" per element
    lines_lst = [ln.rstrip("\n") for ln in lines_lst]

    section_line = f'[{section}]'

    # Detect equal format from a representative existing key line (first line with '=' that isn't a section/comment)
    equal_format = ' = '
    for ln in lines_lst:
        s = ln.strip()
        if not s or s.startswith(("#", ";")):
            continue
        if s.startswith("[") and s.endswith("]"):
            continue
        if "=" in ln:
            # Preserve spacing if it clearly looks like " = " in the actual line
            equal_format = " = " if " = " in ln else "="
            break

    variable_line_to_add = f"{variable}{equal_format}{value}"

    # See if the section is already there (safe detection)
    section_is_there = any(ln.strip() == section_line for ln in lines_lst)

    new_lines_lst = []

    if section_is_there:
        for ln in lines_lst:
            new_lines_lst.append(ln)
            if ln.strip() == section_line:
                new_lines_lst.append(variable_line_to_add)
    else:
        new_lines_lst = list(lines_lst)
        # If file has content and doesn't already end with a blank line, add a blank line before new section
        if new_lines_lst and new_lines_lst[-1].strip() != "":
            new_lines_lst.append("")
        new_lines_lst.append(section_line)
        new_lines_lst.append(variable_line_to_add)

    fileUtils.ensure_file_writable_if_exists(path)

    with open(path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(new_lines_lst) + "\n")


def config_set_variable(cfg_file_path: Union[str, Path], section: str, variable: str, value: str):
    """
    Expects file to already have the section and variable. It just needs to be set to new value.

    Preserves the '=' spacing style from the existing key line (e.g. 'k=v' stays 'k=v',
    'k = v' stays 'k = v'). Falls back to ' = ' if it can't detect.
    """
    path = Path(cfg_file_path)

    lines_lst = fileUtils.read_file(path)
    lines_lst = [ln.rstrip("\n") for ln in lines_lst]

    section_header = f"[{section}]"
    in_good_section = False

    new_lines_lst = []
    replaced = False

    for ln in lines_lst:
        stripped = ln.strip()

        # Section header handling
        if stripped.startswith("[") and stripped.endswith("]"):
            in_good_section = (stripped == section_header)
            new_lines_lst.append(ln)
            continue

        if in_good_section and not replaced:
            # Skip pure comments / blanks
            if stripped and not stripped.startswith(("#", ";")) and "=" in ln:
                left, right = ln.split("=", 1)
                key = left.strip()
                if key == variable:
                    # Preserve the original separator style
                    sep = " = " if " = " in ln else "="
                    new_lines_lst.append(f"{variable}{sep}{value}")
                    replaced = True
                    continue

        new_lines_lst.append(ln)

    # Under your assumption, replaced should always be True here.
    # If you'd prefer a hard fail during refactor, uncomment:
    # if not replaced:
    #     raise KeyError(f"Variable '{variable}' not found in section [{section}] ({path})")

    fileUtils.ensure_file_writable_if_exists(path)

    with open(path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(new_lines_lst) + "\n")


def config_set_add_variable(cfg_file_path, section, variable, value):
    """
    Don't know if something is there already, add if not else set
    """
    tool_name = 'config_set_add_variable'
    return_val = config_section_map(cfg_file_path, section, variable, bypass_error=True)
    if show_verbose:
        log(Severity.DEBUG, tool_name, f'Return Value: "{return_val}"')
    if return_val is None:
        if show_verbose:
            log(Severity.DEBUG, tool_name, 'Variable is None, adding variable...')
        config_add_variable(cfg_file_path, section, variable, value)
    else:
        if show_verbose:
            log(Severity.DEBUG, tool_name, 'Variable exists, setting variable...')
        config_set_variable(cfg_file_path, section, variable, value)


def config_remove_section(cfg_file_path, section):
    """
    Remove a section from a config file
    """
    tool_name = 'config_remove_section'
    line_lst = fileUtils.read_file(cfg_file_path)
    new_line_lst = []
    section_str = f'[{section}]'
    in_right_section = False
    for line in line_lst:
        if line.startswith(section_str):
            in_right_section = True
        elif not in_right_section:
            new_line_lst.append(line + '\n')
        else:
            if line.startswith('['):
                in_right_section = False
                new_line_lst.append(line + '\n')

    fileUtils.write_file(cfg_file_path, new_line_lst)

