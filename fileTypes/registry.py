"""Process-wide, extensible file resolution without GUI or project dependencies."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Callable

from ..fileUtils import File

_registration_owner = ContextVar('file_type_registration_owner', default=None)


def validate_resolution_rule(extensions, detector):
    """Normalize suffixes and validate the same rule for declarations and registration."""
    extensions = (extensions,) if isinstance(extensions, str) else tuple(extensions)
    normalized = tuple(dict.fromkeys(extension.lower().lstrip('.') for extension in extensions))
    if any(not extension or '/' in extension or '\\' in extension for extension in normalized):
        raise ValueError('Extensions must be non-empty suffixes without path separators')
    if detector is not None and not callable(detector):
        raise TypeError('A file detector must be callable')
    if not normalized and detector is None:
        raise ValueError('Supply extensions or a detection rule')
    return normalized


@dataclass(frozen=True)
class FileTypeRegistration:
    file_class: type[File]
    extensions: tuple[str, ...]
    detector: Callable[[Path], bool] | None = None
    priority: int = 0
    owner: str | None = None


def _validate_override_classes(base_class, file_class):
    if not isinstance(base_class, type) or not issubclass(base_class, File):
        raise TypeError('The overridden type must derive from File')
    if not isinstance(file_class, type) or file_class is base_class or not issubclass(file_class, base_class):
        raise TypeError('A replacement must be a subclass of the overridden type')


@dataclass(frozen=True)
class FileTypeOverrideRegistration:
    base_class: type[File]
    file_class: type[File]
    priority: int = 0
    owner: str | None = None


class FileTypeRegistry:
    """Higher priority wins; the most recent registration breaks equal-priority ties."""

    def __init__(self):
        self._registrations = []
        self._overrides = []
        self._lock = RLock()
        self.revision = 0
        self._disabled_owners = set()

    def register(self, file_class, extensions=(), *, detector=None, priority=0, owner=None):
        if not isinstance(file_class, type) or not issubclass(file_class, File):
            raise TypeError('Registered types must derive from File')
        normalized = validate_resolution_rule(extensions, detector)
        owner = owner if owner is not None else _registration_owner.get()
        registration = FileTypeRegistration(file_class, normalized, detector, priority, owner)
        with self._lock:
            if registration in self._registrations:
                return registration
            self._registrations.append(registration)
            self.revision += 1
        return registration

    def register_override(self, base_class, file_class, *, priority=0, owner=None):
        """Replace an exact resolved type with its subclass, independently of suffix rules."""
        _validate_override_classes(base_class, file_class)
        owner = owner if owner is not None else _registration_owner.get()
        registration = FileTypeOverrideRegistration(base_class, file_class, priority, owner)
        with self._lock:
            if registration in self._overrides:
                return registration
            self._overrides.append(registration)
            self.revision += 1
        return registration

    def unregister(self, registration):
        with self._lock:
            entries = self._overrides if isinstance(registration, FileTypeOverrideRegistration) else self._registrations
            entries.remove(registration)
            self.revision += 1

    @contextmanager
    def owner_scope(self, owner):
        """Attribute registrations made by a plugin hook to that owner."""
        token = _registration_owner.set(owner)
        try:
            yield
        finally:
            _registration_owner.reset(token)

    def set_owner_enabled(self, owner, enabled):
        """Toggle resolution without losing rules or changing their priority order."""
        with self._lock:
            if (owner not in self._disabled_owners) == enabled:
                return
            if enabled:
                self._disabled_owners.discard(owner)
            else:
                self._disabled_owners.add(owner)
            self.revision += 1

    def resolve(self, path):
        path = Path(path)
        with self._lock:
            registrations = tuple(entry for entry in self._registrations
                                  if entry.owner not in self._disabled_owners)
            overrides = tuple(entry for entry in self._overrides
                              if entry.owner not in self._disabled_owners)
        # Reversing before the stable sort retains newest-first priority ties.
        candidates = sorted(reversed(registrations), key=lambda entry: entry.priority, reverse=True)
        name = path.name.lower()
        selected = File
        for entry in candidates:
            if entry.extensions and not any(name.endswith('.' + extension) for extension in entry.extensions):
                continue
            if entry.detector is not None and not entry.detector(path):
                continue
            selected = entry.file_class
            break
        # Override exact classes only: TXT replacements must not erase CSV/JSON/
        # Markdown specialization. Strict subclass validation makes chains acyclic.
        replacements = sorted(reversed(overrides), key=lambda entry: entry.priority, reverse=True)
        while True:
            replacement = next((entry.file_class for entry in replacements if entry.base_class is selected), None)
            if replacement is None:
                return selected
            selected = replacement

    def create(self, path):
        return self.resolve(path)(Path(path))


file_types = FileTypeRegistry()
_defaults_lock = RLock()
_defaults_loaded = False


def register_file_type(file_class, extensions=(), *, detector=None, priority=0, owner=None):
    """Register for all future resolutions in this process, not just one directory."""
    return file_types.register(file_class, extensions, detector=detector, priority=priority, owner=owner)


def override_file_type(base_class, file_class, *, priority=0, owner=None):
    """Declare a subclass replacement separately from extension/detector registration.

    Applies to future registry resolution, including existing Directory objects;
    direct constructors and already-created objects retain their original class.
    """
    register_builtin_file_types()
    return file_types.register_override(base_class, file_class, priority=priority, owner=owner)


def register_builtin_file_types():
    """Idempotently load the format modules; external equal-priority rules win."""
    global _defaults_loaded
    with _defaults_lock:
        if _defaults_loaded:
            return
        from . import txtType, csvType, jsonType, xmlType, zipType, dmgType, appimageType, markdownType, iniType
        _defaults_loaded = True


def file_from_path(path):
    register_builtin_file_types()
    return file_types.create(path)


def object_from_path(path):
    """Return a Directory or a resolved File, keeping classification in the data layer."""
    from ..dirUtils import Directory
    path = Path(path)
    return Directory(path) if path.is_dir() else file_from_path(path)
