"""Structural contracts for virtual resources; no backend or UI dependencies.

Paths identify resources inside a provider and need not exist on disk. Consumers
must perform I/O through the provider. See ui/resource-providers.md for lifecycle,
threading, cancellation and publication requirements.
"""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, ContextManager, Protocol, TypedDict


class ResourceRow(TypedDict):
    name: str
    path: str
    directory: bool
    size: int
    modified: str


class DirectoryProvider(Protocol):
    root: Path

    def relative(self, path: str | Path) -> str: ...
    def list(self, path: str | Path = '', *, cancelled: Callable[[], bool]) -> list[ResourceRow]: ...


@dataclass(frozen=True)
class ResourceCapabilities:
    create: bool = False
    rename: bool = False
    delete: bool = False
    replace: bool = False


def capabilities(provider):
    """Undeclared providers are read-only, irrespective of inherited methods."""
    return getattr(provider, 'capabilities', ResourceCapabilities())


def require_capability(provider, operation):
    if not getattr(capabilities(provider), operation):
        raise PermissionError(f'This storage does not support {operation}.')


class ResourceEntry(ResourceRow):
    revision: object


class WritableDirectoryProvider(DirectoryProvider, Protocol):
    storage_id: str
    storage_namespace: str
    capabilities: ResourceCapabilities

    def entry(self, path: str | Path) -> ResourceEntry: ...
    def open(self, path: str | Path) -> ContextManager[BinaryIO]: ...
    def mkdir(self, path: str | Path) -> None: ...
    def create_file(self, path: str | Path, stream: BinaryIO, *, cancelled: Callable[[], bool]) -> None: ...
    def rename(self, source: str | Path, destination: str | Path) -> None: ...
    def remove_empty(self, path: str | Path, revision: object) -> None: ...
    def replace_created(self, staged: str | Path, path: str | Path, expected_revision: object) -> None: ...


class ArchiveSource(Protocol):
    def version(self, path: str | Path) -> object: ...
    def open(self, path: str | Path) -> ContextManager[BinaryIO]: ...


class WritableArchiveSource(ArchiveSource, Protocol):
    def replace_stream(self, path: str | Path, writer: Callable[[BinaryIO], object], *,
                       expected_revision: object, verify: Callable[[Path], object] | None = None) -> None: ...



from .paths import resource_path
