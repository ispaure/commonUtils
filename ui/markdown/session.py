"""Document state independent of Markdown widgets and presentation."""
from dataclasses import dataclass
from pathlib import Path

from .io import _encode_markdown


@dataclass
class MarkdownDocumentState:
    """One open draft and its exact saved/rich-import baselines.

    The source editor owns text and undo history. This object owns persisted
    bytes, identity and synchronization baselines, never a second editable buffer.
    Navigation history and Qt selections remain presentation concerns.
    """
    loaded_path: Path | None = None
    source_bytes: bytes | None = None
    rich_source: str | None = None
    rich_snapshot: str | None = None
    save_pending: bool = False

    def reset_rich(self):
        self.rich_source = None
        self.rich_snapshot = None

    def load(self, path, data):
        self.loaded_path = path
        self.source_bytes = data
        self.reset_rich()

    def new(self):
        self.loaded_path = None
        self.source_bytes = None
        self.reset_rich()

    def capture(self, text, modified):
        return _encode_markdown(text, self.source_bytes, modified)

    def begin_save(self, allowed):
        if not allowed or self.save_pending:
            return False
        self.save_pending = True
        return True
