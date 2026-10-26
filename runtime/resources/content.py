"""Retained document content over providers and caller-supplied content factories.

A factory may be a class or function. It owns decoding and optional native
archive access; it never selects a format editor or a persistence policy.
"""
from contextlib import contextmanager, nullcontext

from .archives import BoundedArchive
from ..operations import check_cancelled


class ProviderContent:
    max_read = 16 * 1024 * 1024

    def __init__(self, provider, path, *, password='', cancelled=lambda: False):
        self.provider = provider.reopen() if hasattr(provider, 'reopen') else provider
        self.path = self.provider.relative(path)
        self.password, self.cancelled = password, cancelled
        self.closed = False
        self.backend = None
        self._release = (self.provider.close if self.provider is not provider and hasattr(self.provider, 'close')
                         else lambda: None)
        try:
            if hasattr(self.provider, 'acquire'):
                self._release = self.provider.acquire()
            self.expected = self.provider.entry(self.path)['revision']
            factory = getattr(self.provider, 'content_source', None)
            if factory is not None:
                self.backend = factory(self.path, password=password, cancelled=cancelled)
            self.check()
        except BaseException:
            self.close()
            raise

    @property
    def private(self):
        return getattr(self.provider, 'private', False)

    def check(self):
        check_cancelled(self.cancelled)
        self.check_access()
        if self.provider.entry(self.path)['revision'] != self.expected:
            raise ValueError('The document changed; reopen it.')

    def check_access(self):
        if self.closed:
            raise ValueError('This document content is closed.')
        check = getattr(self.provider, 'check', None) or getattr(self.provider, '_check_active', None)
        if check is not None:
            check()

    def version(self, path):
        if self.provider.relative(path) != self.path:
            raise ValueError('This content source owns a different document.')
        self.check()
        return self.expected

    @contextmanager
    def operation(self):
        operation = getattr(self.provider, 'operation', None)
        with operation(self.cancelled) if operation else nullcontext():
            self.check()
            yield
            self.check()

    @contextmanager
    def open(self, path):
        self.version(path)
        with self.operation():
            source = self.backend or self.provider
            with source.open(self.path) as stream:
                yield stream

    @contextmanager
    def open_archive(self, path, password=None):
        self.version(path)
        with self.operation():
            source = self.backend or self.provider
            archive = getattr(source, 'open_archive', None)
            if archive is not None:
                with archive(self.path, password=self.password if password is None else password) as opened:
                    yield opened
            else:
                from ...archives.zip_access import open_archive, validate_members
                with self.open(self.path) as stream, open_archive(stream, password=password or self.password or None) as opened:
                    validate_members(opened)
                    if len(opened.infolist()) > 10000:
                        raise ValueError('Archive contains too many entries.')
                    yield BoundedArchive(opened, self)

    def archive_password(self, path):
        return self.password or None

    def close(self):
        if not self.closed:
            self.closed = True
            self.password = None
            try:
                if self.backend is not None:
                    self.backend.close()
            finally:
                self._release()
