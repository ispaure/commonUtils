"""Storage-independent Open/Save selection and document sessions (no widgets)."""
from dataclasses import dataclass
from contextlib import nullcontext
from pathlib import Path
from .paths import resource_path
from .provider import require_capability
from ..operations import check_cancelled
from ..streams import read_up_to
from .mutations import save_resource_and_reopen
from ...persistence.text import TextSession


@dataclass
class ResourceChoice:
    provider: object
    path: str
    release: object = lambda: None

    def close(self):
        release, self.release = self.release, lambda: None
        release()


class ResourceSelection:
    def __init__(self, provider, *, mode='open', extensions=()):
        if mode not in {'open', 'save', 'destination'}:
            raise ValueError('Unknown resource selection mode.')
        self.provider, self.mode = provider, mode
        self.extensions = tuple(extensions)
        self.root = provider.root

    def relative(self, path):
        return self.provider.relative(path)

    def list(self, path='', *, cancelled=lambda: False):
        # A picker may omit unavailable local entries without weakening recursive
        # mutation inventories on the actual provider.
        from .local import LocalFiles
        if type(self.provider) is LocalFiles:
            rows = []
            for child in self.provider._locate(path).iterdir():
                check_cancelled(cancelled)
                try:
                    rows.append(self.provider.entry(child))
                except (ValueError, OSError):
                    continue
        else:
            rows = self.provider.list(path, cancelled=cancelled)
        return sorted((row for row in rows if row['directory'] or not self.extensions
                       or Path(row['name']).suffix.lower() in self.extensions),
                      key=lambda row: (not row['directory'], row['name'].casefold()))

    def resolve(self, directory, name, *, cancelled=lambda: False):
        check_cancelled(cancelled)
        directory = self.relative(directory)
        name = resource_path(name)
        if not name:
            raise ValueError('Choose a file name.')
        path = '/'.join(part for part in (directory, name) if part)
        if self.extensions and Path(path).suffix.lower() not in self.extensions:
            raise ValueError('Choose a supported file type: ' + ', '.join(self.extensions))
        if self.mode == 'open':
            if self.provider.entry(path)['directory']:
                raise ValueError('Open the folder and select a file.')
        else:
            for capability in ('create', 'rename', 'delete'):
                require_capability(self.provider, capability)
            parent = path.rpartition('/')[0]
            if not self.provider.entry(parent)['directory']:
                raise ValueError('The destination folder does not exist.')
            try:
                self.provider.entry(path)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError('A destination with this name already exists. Choose another name.')
        check_cancelled(cancelled)
        return path


class ResourceTextSession:
    """A bounded provider text draft baseline; never writes recovery or recents."""
    def __init__(self, provider, path, text):
        self.provider, self.path, self.text = provider, path, text

    @classmethod
    def open(cls, provider, path, *, max_bytes=1024 * 1024, cancelled=lambda: False):
        path = provider.relative(path)
        before = provider.entry(path)['revision']
        scope = getattr(provider, 'operation', None)
        with scope(cancelled) if scope else nullcontext():
            with provider.open(path) as stream:
                data = read_up_to(stream, max_bytes + 1, cancelled=cancelled)
        check_cancelled(cancelled)
        if provider.entry(path)['revision'] != before:
            raise ValueError('The document changed while opening; reopen it.')
        return cls(provider, path, TextSession(Path(path).name, data, key=path,
                                               revision=before, max_bytes=max_bytes))

    def save(self, draft, *, cancelled=lambda: False):
        return self.publish(self.provider, self.path, self.text.encode(draft),
                            expected_revision=self.text.revision, cancelled=cancelled)

    def save_as(self, provider, path, draft, *, cancelled=lambda: False):
        return self.publish(provider, path, self.text.encode(draft), cancelled=cancelled)

    def publish(self, provider, path, data, *, expected_revision=None, cancelled=lambda: False):
        def reopen():
            updated = self.open(provider, path, max_bytes=self.text.max_bytes)
            if updated.text.data != data:
                raise ValueError('The saved file changed after publication.')
            return updated
        return save_resource_and_reopen(provider, path, data, reopen=reopen,
                                        expected_revision=expected_revision, cancelled=cancelled)
