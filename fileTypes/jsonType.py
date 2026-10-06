"""UTF-8 JSON files with atomic writes and standard parsing errors."""

import json
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile

from ..fileUtils import File


class JSONFile(File):
    """Read JSON values and replace files only after serialization succeeds."""

    def __init__(self, path):
        super().__init__(Path(path))

    def read_json(self):
        """Return the parsed value; missing/malformed files raise standard errors."""
        with self.path.open('r', encoding='utf-8-sig') as stream:
            return json.load(stream)

    def write_json(self, value, *, compact=False, sort_keys=False, ensure_ascii=False):
        """Atomically write valid JSON, keeping an existing file on any failure.

        Parent directories are created as needed. Existing file permissions are
        preserved; new files use the temporary file's private permissions.
        """
        text = json.dumps(value, ensure_ascii=ensure_ascii, sort_keys=sort_keys,
                          allow_nan=False, separators=(',', ':') if compact else None,
                          indent=None if compact else 2)
        try:
            permissions = stat.S_IMODE(self.path.stat().st_mode)
        except FileNotFoundError:
            permissions = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staged = None
        try:
            with NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                    prefix=f'.{self.path.name}-', suffix='.tmp', delete=False) as stream:
                staged = Path(stream.name)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            if permissions is not None:
                staged.chmod(permissions)
            os.replace(staged, self.path)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)
        self.size = self.path.stat().st_size


from .registry import register_file_type
register_file_type(JSONFile, 'json', priority=-100)
