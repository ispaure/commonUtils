"""Application-supplied configuration; generic Perforce models import no host code."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from dataclasses import dataclass
from collections.abc import Callable, Mapping
from pathlib import Path
import shutil
from ....runtime.platform import OS


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
