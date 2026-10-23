"""UTF-8 JSON files with atomic writes and standard parsing errors."""

import json
import os
from pathlib import Path

from ..filesystem.files import File
from ..filesystem.local_access import check_local_path
from ..persistence import atomic_write_bytes


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
        content = text.replace('\n', os.linesep).encode('utf-8')
        check_local_path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(self.path, content)
        self.size = len(content)


from .registry import register_file_type
register_file_type(JSONFile, 'json', priority=-100)
