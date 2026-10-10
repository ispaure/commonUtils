"""Versioned, bounded, atomic private JSON checkpoints without Qt dependencies."""
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

MAX_SESSION_BYTES = 64 * 1024 * 1024


class SessionStore:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        with self.path.open("rb") as stream:
            data = stream.read(MAX_SESSION_BYTES + 1)
        if len(data) > MAX_SESSION_BYTES:
            raise ValueError("Session checkpoint exceeds 64 MiB.")
        payload = json.loads(data)
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("Unsupported session checkpoint.")
        documents = payload.get("documents")
        if not isinstance(documents, list) or len(documents) > 100:
            raise ValueError("Session checkpoint must contain at most 100 documents.")
        return payload

    def write(self, payload):
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        if len(data) > MAX_SESSION_BYTES:
            raise ValueError("Session checkpoint exceeds 64 MiB.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile("wb", dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            if os.name != "nt":
                descriptor = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
