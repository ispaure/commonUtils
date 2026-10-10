"""Application-supplied configuration; generic Perforce models import no host code."""
from dataclasses import dataclass
from collections.abc import Callable, Mapping
from pathlib import Path
import shutil
from ...osUtils import OS


def _executable(platform):
    return shutil.which('p4') or 'p4'


@dataclass(frozen=True)
class PerforceRuntime:
    executable: Callable[[OS], str] = _executable
    environment: Callable[[], Mapping[str, str]] = lambda: {}
    binary_template: Callable[[], Path | None] = lambda: None


_runtime = PerforceRuntime()


def configure_runtime(configuration=None):
    """Install lazy host callbacks; None restores command-line defaults."""
    global _runtime
    _runtime = configuration if configuration is not None else PerforceRuntime()


def runtime():
    return _runtime
