"""Versioned, bounded, atomic private JSON checkpoints without Qt dependencies."""
import json
import os
from pathlib import Path
from . import atomic_write_json

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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, payload, ensure_ascii=True, allow_nan=True,
                          max_bytes=MAX_SESSION_BYTES, durable_directory=True)
