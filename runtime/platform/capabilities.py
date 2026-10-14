"""Conservative adapter policy, independent of Qt and desktop initialization.

IMPLEMENTED means an existing desktop adapter, not a successful runtime probe.
Only explicit, operation-specific probes may report VERIFIED. Never use this
policy as an access-control or permission check.
"""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from tempfile import TemporaryFile
import weakref

from . import OS, get_os


class Capability(Enum):
    FILESYSTEM = 'filesystem access'
    SUBPROCESS = 'subprocesses'
    SHELL = 'shell integration'
    EXTERNAL_APPLICATIONS = 'external application launching'
    FILE_DIALOGS = 'file dialogs'
    DESKTOP_UI = 'desktop UI'
    QT_UI = 'hosted Qt UI'
    DEFAULT_STORAGE = 'desktop storage defaults'


class CapabilityState(Enum):
    IMPLEMENTED = 'implemented'
    VERIFIED = 'verified'
    UNVERIFIED = 'unverified'
    UNAVAILABLE = 'unavailable'


@dataclass(frozen=True)
class CapabilityStatus:
    state: CapabilityState
    reason: str


class UnsupportedCapabilityError(RuntimeError):
    """An operation has no usable adapter in the current runtime."""


_qt_host = None


def register_qt_ui_host(application):
    """Admit Qt widgets for an explicitly supplied Qt 6.12+ mobile host.

    This does not admit desktop dialogs, storage, subprocesses or external apps,
    and does not certify any individual widget or operation on a device.
    Call on the application's GUI thread before importing commonUtils UI.
    """
    from PySide6.QtCore import QThread, qVersion
    from PySide6.QtWidgets import QApplication
    if not isinstance(application, QApplication) or QApplication.instance() is not application:
        raise ValueError('Supply the live QApplication instance')
    if application.thread() != QThread.currentThread():
        raise ValueError('Register the Qt host on its GUI thread')
    if tuple(int(part) for part in qVersion().split('.')[:2]) < (6, 12):
        raise ValueError('Mobile Qt hosts require Qt 6.12 or newer')
    global _qt_host
    _qt_host = weakref.ref(application)


def sandbox_restrictions() -> bool | None:
    """True for mobile policy; None means desktop restrictions are unknown.

    Desktop processes can also be sandboxed. False is never inferred from OS.
    """
    return True if get_os() in (OS.IOS, OS.ANDROID) else None


def capability_status(capability: Capability) -> CapabilityStatus:
    capability = Capability(capability)
    current = get_os()
    if capability is Capability.FILESYSTEM:
        return CapabilityStatus(CapabilityState.UNVERIFIED,
                                'Access is path-specific; probe or perform the requested operation.')
    if current in (OS.IOS, OS.ANDROID):
        if capability is Capability.QT_UI and _qt_host is not None:
            host = _qt_host()
            if host is not None:
                from shiboken6 import isValid
                if isValid(host):
                    return CapabilityStatus(CapabilityState.IMPLEMENTED,
                                            'Explicit Qt host; widget operations still require validation.')
        return CapabilityStatus(CapabilityState.UNAVAILABLE,
                                f'No verified {current.value} adapter; the host must provide mobile integration.')
    return CapabilityStatus(CapabilityState.IMPLEMENTED,
                            'Existing desktop adapter; runtime dependencies and permissions still apply.')


def require_capability(capability: Capability, operation: str = '') -> None:
    """Reject unimplemented/unverified operations before desktop side effects.

    Existing desktop adapters retain their own error and dependency behavior.
    """
    capability = Capability(capability)
    status = capability_status(capability)
    if status.state not in (CapabilityState.IMPLEMENTED, CapabilityState.VERIFIED):
        raise UnsupportedCapabilityError(
            f'{operation or capability.value}: {capability.value} unavailable on '
            f'{get_os().value}. {status.reason}')


def probe_filesystem(path: str | Path, *, write: bool = False) -> CapabilityStatus:
    """Try reading a file/listing a directory, or creating a temporary file there.

    A write probe requires a directory and removes only its own temporary file.
    Results cover this operation/path at this instant, never arbitrary filesystem
    access, future permissions, atomic replacement, durability or document URIs.
    """
    path = Path(path)
    try:
        if write:
            with TemporaryFile(dir=path) as stream:
                stream.write(b'commonUtils probe')
                stream.flush()
        elif path.is_dir():
            next(path.iterdir(), None)
        else:
            with path.open('rb') as stream:
                stream.read(1)
    except OSError as error:
        return CapabilityStatus(CapabilityState.UNAVAILABLE, f'{path}: {error}')
    return CapabilityStatus(CapabilityState.VERIFIED,
                            f'{"Temporary-file write" if write else "Read"} succeeded at {path}.')
