"""Repository defaults and sparse personal overrides, without GUI dependencies.

Reads never create files. Saves preserve unrelated settings and detect concurrent
edits. A None update removes a personal override rather than copying a default.
Hosts register their own default/personal path pairs; commonUtils owns no feature
discovery or application configuration directories.
"""
from configparser import Error
from pathlib import Path
from functools import lru_cache
import re
import os
import sys

from ..formats.iniType import INIFile

_personal_paths = {}


def shared_settings():
    """Shared UI defaults and persistent platform-standard personal settings."""
    from .settings import settings_path
    defaults = settings_path()
    personal = personal_path(defaults)
    if personal is None:
        from ..runtime.platform.capabilities import Capability, require_capability
        require_capability(Capability.DEFAULT_STORAGE, 'shared_settings; register a personal settings path first')
        if sys.platform == 'darwin':
            folder = Path.home() / 'Library' / 'Application Support' / 'commonUtils'
        elif sys.platform == 'win32':
            folder = Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming') / 'commonUtils'
        else:
            base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
            folder = (base if base.is_absolute() else Path.home() / '.config') / 'commonUtils'
        personal = folder / 'settings.ini'
    return register_settings(defaults, personal)


def register_settings(defaults, personal):
    """Associate a defaults INI with its host-owned personal INI. Return a store."""
    defaults, personal = Path(defaults).resolve(), Path(personal).resolve()
    if defaults == personal:
        raise ValueError('Defaults and personal settings must use different files')
    _personal_paths[defaults] = personal
    return LayeredSettings(defaults, personal)


def personal_path(defaults):
    return _personal_paths.get(Path(defaults).resolve())


def read_values(path):
    """Read explicit INI fields. Missing files are empty; malformed files raise."""
    path = Path(path)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {}
    return dict(_read_values(path, (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)))


@lru_cache(maxsize=64)
def _read_values(path, stamp):
    parser = INIFile.parse(path.read_text(encoding='utf-8-sig'))
    return {(section, key): value for section in parser.sections()
            for key, value in parser[section].items()}


def effective_settings(path, *, case_sensitive=True, allow_duplicates=False,
                       normalize_after_parse=True):
    """Compose registered layers with explicit legacy parser policies.

    Canonical callers normalize after case-preserving parsing. Legacy callers
    parse with their requested case/duplicate policy before the same overlay.
    """
    from .composition import parse_defaults, overlay
    parser = parse_defaults(path, case_sensitive=case_sensitive,
                            allow_duplicates=allow_duplicates,
                            normalize_after_parse=normalize_after_parse)
    personal = personal_path(path)
    if personal is not None:
        try:
            values = read_values(personal)
        except (OSError, UnicodeError, Error):
            values = {}
        overlay(parser, values)
    return parser


def remove_fields(text, fields):
    """Remove explicit options and their continuations, retaining comments."""
    parser = INIFile.parse(text)
    fields = set(fields)
    lines, section, skipping = [], 'DEFAULT', False
    for line in text.splitlines(keepends=True):
        header = re.match(r'^\s*\[([^]]+)\]', line)
        option = re.match(r'^([^\s#;][^=:\r\n]*?)\s*[=:]', line)
        if header:
            section, skipping = header[1], False
        elif option:
            skipping = (section, option[1].strip()) in fields
            if skipping:
                continue
        elif skipping and line[:1].isspace() and line.strip() and not line.lstrip().startswith(('#', ';')):
            continue
        lines.append(line)
    result = ''.join(lines)
    actual = INIFile.parse(result)
    for section, key in fields:
        if parser.has_section(section):
            parser.remove_option(section, key)
    if any(dict(actual[s]) != dict(parser[s]) for s in parser.sections()):
        raise ValueError('Cannot safely remove an override from this INI layout')
    return result


class LayeredSettings:
    def __init__(self, defaults, personal):
        self.defaults = Path(defaults)
        self.personal = Path(personal)
        if self.defaults.resolve() == self.personal.resolve():
            raise ValueError('Defaults and personal settings must use different files')

    def path(self, scope):
        if scope not in ('application', 'personal'):
            raise ValueError('Settings scope must be application or personal')
        return self.defaults if scope == 'application' else self.personal

    def values(self, scope='personal'):
        values = read_values(self.defaults)
        if scope == 'personal':
            values.update(read_values(self.personal))
        elif scope != 'application':
            raise ValueError('Settings scope must be application or personal')
        return values

    def overrides(self):
        return read_values(self.personal)

    def save(self, changes, *, scope='personal', expected=None):
        """Apply strings/None to one layer; expected bytes protect dirty UI edits."""
        path = self.path(scope)
        current = path.read_bytes() if path.exists() else None
        if expected is not None and current != expected[0]:
            raise OSError('Settings changed on disk; reload before saving')
        ini = INIFile(path)
        if current is not None:
            ini.read()
        removals = [key for key, value in changes.items() if value is None]
        if scope == 'application' and removals:
            raise ValueError('Software defaults cannot be removed by resetting personal fields')
        text = remove_fields(ini.text, removals) if removals else ini.text
        ini.text = INIFile.updated_text(text, {key: value for key, value in changes.items() if value is not None})
        # Parse before touching the filesystem. INIFile.save checks the original
        # bytes again and atomically preserves encoding, line endings and mode.
        INIFile.parse(ini.text)
        ini.save()
        from .monitor import settings_monitor
        settings_monitor().notify((path,))

    def safe_values(self, scope='personal'):
        try:
            return self.values(scope)
        except (OSError, UnicodeError, Error):
            return {}
