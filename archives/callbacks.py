"""Read-only ZIP-compatible views backed by explicit member callbacks."""

from contextlib import contextmanager
from io import BytesIO
from typing import Callable, Iterable
from zipfile import ZipInfo
from ..runtime.operations import check_cancelled


class CallbackArchive:
    def __init__(
        self,
        members: Iterable[ZipInfo],
        *,
        read_member: Callable[[str], bytes],
        manifest: Callable[[], dict] | None = None,
    ):
        self.members = list(members)
        self._read_member = read_member
        self._manifest = manifest

    def content_manifest(self, *, cancelled=lambda: False):
        check_cancelled(cancelled)
        if self._manifest is None:
            raise ValueError("This archive source does not provide a content manifest.")
        rows = self._manifest()
        check_cancelled(cancelled)
        return {
            name: None if value is None else tuple(value)
            for name, value in rows.items()
        }

    def infolist(self):
        return list(self.members)

    def namelist(self):
        return [member.filename for member in self.members]

    def getinfo(self, name):
        for info in self.members:
            if info.filename == name:
                return info
        raise KeyError(name)

    def read(self, member):
        name = member.filename if isinstance(member, ZipInfo) else member
        self.getinfo(name)
        return self._read_member(name)

    @contextmanager
    def open(self, member, *args, **kwargs):
        with BytesIO(self.read(member)) as stream:
            yield stream
