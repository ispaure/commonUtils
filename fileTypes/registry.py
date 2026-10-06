"""Process-wide, extensible file resolution without GUI or project dependencies."""

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Callable

from ..fileUtils import File


@dataclass(frozen=True)
class FileTypeRegistration:
    file_class: type[File]
    extensions: tuple[str, ...]
    detector: Callable[[Path], bool] | None = None
    priority: int = 0


class FileTypeRegistry:
    """Higher priority wins; the most recent registration breaks equal-priority ties."""

    def __init__(self):
        self._registrations = []
        self._lock = RLock()
        self.revision = 0

    def register(self, file_class, extensions=(), *, detector=None, priority=0):
        if not isinstance(file_class, type) or not issubclass(file_class, File):
            raise TypeError('Registered types must derive from File')
        if isinstance(extensions, str):
            extensions = (extensions,)
        normalized = tuple(dict.fromkeys(extension.lower().lstrip('.') for extension in extensions))
        if any(not extension or '/' in extension or '\\' in extension for extension in normalized):
            raise ValueError('Extensions must be non-empty suffixes without path separators')
        if detector is not None and not callable(detector):
            raise TypeError('A file detector must be callable')
        if not normalized and detector is None:
            raise ValueError('Supply extensions or a detection rule')
        registration = FileTypeRegistration(file_class, normalized, detector, priority)
        with self._lock:
            if registration in self._registrations:
                return registration
            self._registrations.append(registration)
            self.revision += 1
        return registration

    def unregister(self, registration):
        with self._lock:
            self._registrations.remove(registration)
            self.revision += 1

    def resolve(self, path):
        path = Path(path)
        with self._lock:
            registrations = tuple(self._registrations)
        candidates = sorted(enumerate(registrations), key=lambda item: (item[1].priority, item[0]), reverse=True)
        name = path.name.lower()
        for _, entry in candidates:
            if entry.extensions and not any(name.endswith('.' + extension) for extension in entry.extensions):
                continue
            if entry.detector is not None and not entry.detector(path):
                continue
            return entry.file_class
        return File

    def create(self, path):
        return self.resolve(path)(Path(path))


file_types = FileTypeRegistry()
_defaults_lock = RLock()
_defaults_loaded = False


def register_file_type(file_class, extensions=(), *, detector=None, priority=0):
    """Register for all future resolutions in this process, not just one directory."""
    return file_types.register(file_class, extensions, detector=detector, priority=priority)


def register_builtin_file_types():
    """Idempotently load the format modules; external equal-priority rules win."""
    global _defaults_loaded
    with _defaults_lock:
        if _defaults_loaded:
            return
        from . import txtType, csvType, jsonType, xmlType, zipType, dmgType, appimageType
        _defaults_loaded = True


def file_from_path(path):
    register_builtin_file_types()
    return file_types.create(path)


def object_from_path(path):
    """Return a Directory or a resolved File, keeping classification in the data layer."""
    from ..dirUtils import Directory
    path = Path(path)
    return Directory(path) if path.is_dir() else file_from_path(path)
