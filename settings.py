"""Shared INI settings, with safe defaults and automatic reload after a file edit.

Consumers may use get_setting for basic typed values or the navigation accessor.
Reading settings never creates or rewrites the INI. The settings editor owns saves.
"""
from configparser import ConfigParser, Error
from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from pathlib import Path


def settings_path():
    """INI beside the shared UI/file_browser package."""
    return Path(__file__).resolve().parent / 'ui' / 'settings.ini'


@lru_cache(maxsize=8)
def _read(path, stamp):
    parser = ConfigParser(interpolation=None)
    try:
        parser.read_string(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, Error):
        return ConfigParser(interpolation=None)
    return parser


def get_setting(section, key, default, *, minimum=None, maximum=None, path=None):
    """Read a bool/int/float/string using the default's type; invalid values fall back.

    Missing/unreadable/malformed files also use defaults. Numeric bounds are inclusive.
    Saved edits are picked up on the next read without restarting the application.
    """
    path = Path(path) if path is not None else settings_path()
    try:
        stat = path.stat()
        parser = _read(path, (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))
        if isinstance(default, bool):
            value = parser.getboolean(section, key)
        else:
            value = type(default)(parser.get(section, key))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if (not isfinite(value) or minimum is not None and value < minimum
                    or maximum is not None and value > maximum):
                return default
        return value
    except (OSError, Error, ValueError, OverflowError):
        return default


@dataclass(frozen=True)
class WheelNavigationSettings:
    sensitivity: float = 20.0
    cooldown_ms: int = 250
    immediate_notches: bool = True


def get_wheel_navigation_settings(*, path=None):
    """Settings for interfaces that use a wheel to navigate discrete pages/items."""
    return WheelNavigationSettings(
        sensitivity=get_setting('WheelNavigation', 'sensitivity', 20.0,
                                minimum=1, maximum=100, path=path),
        cooldown_ms=get_setting('WheelNavigation', 'cooldown_ms', 250,
                               minimum=0, maximum=2000, path=path),
        immediate_notches=get_setting('WheelNavigation', 'immediate_notches', True, path=path),
    )
