"""Qt-independent feature declarations; browser bindings are created lazily."""

from dataclasses import dataclass, field
import importlib
from typing import Callable
from weakref import WeakSet

from .fileUtils import File
from .filesystem import FilesystemObject
from .fileTypes.registry import validate_resolution_rule, _validate_override_classes


def resolve_type(value):
    """Resolve an optional 'package.module:Class' reference only when needed."""
    if isinstance(value, str):
        module, _, name = value.partition(':')
        value = getattr(importlib.import_module(module), name)
    if not isinstance(value, type) or not issubclass(value, FilesystemObject):
        raise TypeError('Expected a File/Directory class')
    return value


def _valid_type(value):
    if isinstance(value, str):
        module, separator, name = value.partition(':')
        return bool(separator and module and name and ':' not in name)
    return isinstance(value, type) and issubclass(value, FilesystemObject)


def _accepts(types):
    types = (types,) if isinstance(types, (type, str)) else tuple(types)
    if not types or any(not _valid_type(kind) for kind in types):
        raise TypeError('accepts must contain File/Directory classes or module:Class references')
    return types


@dataclass(frozen=True)
class ActionContext:
    browser: object
    host: object
    controller: object
    selection: tuple

    @property
    def paths(self):
        return tuple(item.path for item in self.selection)

    @property
    def item(self):
        if len(self.selection) != 1:
            raise ValueError('This action requires exactly one item')
        return self.selection[0]

    @property
    def path(self):
        return self.item.path


@dataclass(frozen=True)
class FileType:
    file_class: type[File] | str
    extensions: tuple[str, ...] | str = ()
    detector: Callable | None = None
    priority: int = 0

    def __post_init__(self):
        if not _valid_type(self.file_class) or (isinstance(self.file_class, type) and not issubclass(self.file_class, File)):
            raise TypeError('file_class must derive from File')
        extensions = validate_resolution_rule(self.extensions, self.detector)
        object.__setattr__(self, 'extensions', extensions)


@dataclass(frozen=True)
class FileTypeOverride:
    """Explicit subclass replacement, separate from extension-based FileType rules."""
    base_class: type[File] | str
    file_class: type[File] | str
    priority: int = 0

    def __post_init__(self):
        for value in (self.base_class, self.file_class):
            if not _valid_type(value) or (isinstance(value, type) and not issubclass(value, File)):
                raise TypeError('Override declarations require File classes or module:Class references')
        if isinstance(self.base_class, type) and isinstance(self.file_class, type):
            _validate_override_classes(self.base_class, self.file_class)


@dataclass(frozen=True)
class SelectionAction:
    """handler(context) receives only accepted objects from the captured selection."""
    id: str
    label: str
    accepts: tuple[type | str, ...] | type | str
    handler: Callable
    is_available: Callable | None = None
    category: str = 'tools'
    order: int = 100
    shared_key: str | None = None

    def __post_init__(self):
        if not self.id or not self.label:
            raise ValueError('Actions need an id and label')
        if not callable(self.handler):
            raise TypeError('Action handler must be callable')
        if self.is_available is not None and not callable(self.is_available):
            raise TypeError('Action availability must be callable')
        object.__setattr__(self, 'accepts', _accepts(self.accepts))
        if self.shared_key is not None and (not isinstance(self.shared_key, str) or not self.shared_key):
            raise ValueError('shared_key must be a non-empty action identity')


@dataclass(frozen=True)
class FileActivation:
    """The first matching activation handles a double-clicked file."""
    accepts: tuple[type | str, ...] | type | str
    handler: Callable
    is_available: Callable | None = None

    def __post_init__(self):
        if not callable(self.handler):
            raise TypeError('Activation handler must be callable')
        if self.is_available is not None and not callable(self.is_available):
            raise TypeError('Activation availability must be callable')
        object.__setattr__(self, 'accepts', _accepts(self.accepts))


@dataclass(frozen=True)
class BrowserExtension:
    actions: tuple[SelectionAction, ...] = ()
    activation: tuple[FileActivation, ...] = ()
    folder_fields: Callable | None = None
    create_controller: Callable | None = None

    def __post_init__(self):
        object.__setattr__(self, 'actions', tuple(self.actions))
        object.__setattr__(self, 'activation', tuple(self.activation))
        if any(not isinstance(action, SelectionAction) for action in self.actions):
            raise TypeError('actions must contain SelectionAction declarations')
        if len({action.id for action in self.actions}) != len(self.actions):
            raise ValueError('Action ids must be unique within a feature')
        if any(not isinstance(activation, FileActivation) for activation in self.activation):
            raise TypeError('activation must contain FileActivation declarations')
        for name in ('folder_fields', 'create_controller'):
            value = getattr(self, name)
            if value is not None and not callable(value):
                raise TypeError(f'{name} must be callable')


@dataclass(kw_only=True)
class Feature:
    """One declaration for owned file types and per-window browser capabilities."""
    id: str
    label: str = ''
    requires: tuple[str, ...] = ()
    optional_requires: tuple[str, ...] = ()
    file_types: tuple[FileType, ...] = ()
    file_type_overrides: tuple[FileTypeOverride, ...] = ()
    browser: BrowserExtension | None = None
    initialize: Callable | None = None
    _enabled: bool = field(default=True, init=False, repr=False)
    _bindings: WeakSet = field(default_factory=WeakSet, init=False, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError('Feature id must be a non-empty string')
        if not isinstance(self.label, str):
            raise TypeError('Feature label must be a string')
        self.label = self.label or self.id.replace('_', ' ').title()
        for name in ('requires', 'optional_requires'):
            values = getattr(self, name)
            if isinstance(values, str):
                raise TypeError(f'{name} must contain feature ids')
            values = tuple(values)
            if any(not isinstance(value, str) or not value for value in values):
                raise TypeError(f'{name} must contain feature ids')
            setattr(self, name, tuple(values))
        self.file_types = tuple(self.file_types)
        if any(not isinstance(spec, FileType) for spec in self.file_types):
            raise TypeError('file_types must contain FileType declarations')
        self.file_type_overrides = tuple(self.file_type_overrides)
        if any(not isinstance(spec, FileTypeOverride) for spec in self.file_type_overrides):
            raise TypeError('file_type_overrides must contain FileTypeOverride declarations')
        if self.browser is not None and not isinstance(self.browser, BrowserExtension):
            raise TypeError('browser must be a BrowserExtension')
        if self.initialize is not None and not callable(self.initialize):
            raise TypeError('initialize must be callable')

    @property
    def enabled(self):
        return self._enabled

    def register_types(self):
        """Idempotent, owned registration; never implicitly enable a disabled owner."""
        from .fileTypes.registry import file_types, register_builtin_file_types
        register_builtin_file_types()
        overrides = [(resolve_type(spec.base_class), resolve_type(spec.file_class), spec.priority)
                     for spec in self.file_type_overrides]
        for base_class, file_class, _ in overrides:
            _validate_override_classes(base_class, file_class)
        registrations = tuple(file_types.register(resolve_type(spec.file_class), spec.extensions, detector=spec.detector,
                                                  priority=spec.priority, owner=self.id) for spec in self.file_types)
        return registrations + tuple(file_types.register_override(base_class, file_class, priority=priority, owner=self.id)
                                     for base_class, file_class, priority in overrides)


    def install_browser(self, browser, *, host=None, controller=None):
        """Bind the declaration to a window, using an existing controller if supplied."""
        if self.browser is None:
            raise ValueError(f'Feature {self.id} has no browser extension')
        for binding in tuple(self._bindings):
            if binding.browser is browser:
                if controller is not None and binding.controller is not controller:
                    raise ValueError('This feature already has a different controller in this browser')
                return binding
        self.register_types()
        from .ui.file_browser.extensions import InstalledFeature
        binding = InstalledFeature(self, browser, host=host, controller=controller)
        self._bindings.add(binding)
        return binding

    def set_enabled(self, enabled):
        """Activate owned formats and every live binding; dependency policy belongs to the host."""
        from .fileTypes.registry import file_types
        self._enabled = bool(enabled)
        file_types.set_owner_enabled(self.id, self._enabled)
        for binding in tuple(self._bindings):
            binding.set_enabled(self._enabled)
