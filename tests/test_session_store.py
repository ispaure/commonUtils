import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.session_store import SessionStore


class SessionStoreTests(unittest.TestCase):
    def test_atomic_private_checkpoint_and_failed_promotion(self):
        with TemporaryDirectory() as directory:
            store = SessionStore(Path(directory) / "session.json")
            payload = {"version": 1, "documents": [{"text": "😀"}]}
            store.write(payload)
            self.assertEqual(store.read(), payload)
            if os.name != "nt":
                self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
            with patch("commonUtils.persistence.os.replace", side_effect=OSError("full")):
                with self.assertRaises(OSError):
                    store.write({"version": 1, "documents": []})
            self.assertEqual(store.read(), payload)
            self.assertEqual(list(Path(directory).iterdir()), [store.path])

    def test_corrupt_and_future_schema_are_preserved(self):
        with TemporaryDirectory() as directory:
            store = SessionStore(Path(directory) / "session.json")
            for data in (b'{bad', b'{"version":2,"documents":[]}'):
                store.path.write_bytes(data)
                with self.assertRaises(ValueError):
                    store.read()
                self.assertEqual(store.path.read_bytes(), data)
