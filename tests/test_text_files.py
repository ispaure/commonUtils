import codecs
from pathlib import Path
import tempfile
import unittest
from commonUtils.text_files import (
    decode_bytes,
    read_text_file,
    write_text_file,
    BinaryTextError,
    FileConflictError,
    is_text_path,
)


class TextFilesTests(unittest.TestCase):
    def test_size_limit_bounds_reads_and_writes(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "large.log"
            path.write_bytes(b"x" * 65)
            with patch("commonUtils.text_files.MAX_BYTES", 64):
                with self.assertRaises(ValueError):
                    read_text_file(path)
                with self.assertRaises(ValueError):
                    write_text_file(path, b"y" * 65, expected=b"x" * 65)
            self.assertEqual(path.read_bytes(), b"x" * 65)

    def test_encodings_endings_and_final_newline_round_trip(self):
        for encoding, bom in [
            ("utf-8", b""),
            ("utf-8", codecs.BOM_UTF8),
            ("utf-16-le", codecs.BOM_UTF16_LE),
            ("cp1252", b""),
        ]:
            for newline in ["\n", "\r\n", "\r"]:
                for final in ["", newline]:
                    data = bom + ("café" + newline + "second" + final).encode(encoding)
                    snapshot = decode_bytes(data, encoding=encoding)
                    self.assertEqual(snapshot.encode(snapshot.text), data)
                    self.assertEqual(
                        snapshot.encode(snapshot.text.replace("second", "changed")),
                        bom + ("café" + newline + "changed" + final).encode(encoding),
                    )

    def test_mixed_endings_and_unicode_are_preserved(self):
        snapshot = decode_bytes("😀 one\r\ntwo\rthree\n".encode())
        self.assertTrue(snapshot.mixed_endings)
        self.assertEqual(
            snapshot.encode(snapshot.text.replace("two", "edit")),
            "😀 one\r\nedit\r\nthree\n".encode(),
        )

    def test_binary_legacy_and_force(self):
        with self.assertRaises(BinaryTextError):
            decode_bytes(b"abc\0def")
        self.assertEqual(
            decode_bytes(b"abc\0def", force=True).encode("abc\0def"), b"abc\0def"
        )
        with self.assertRaises(UnicodeError):
            decode_bytes(b"caf\xe9")
        self.assertEqual(decode_bytes(b"caf\xe9", encoding="cp1252").text, "café")

    def test_extensionless_atomic_save_conflicts_and_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_bytes(b"VAR=1\r\n")
            path.chmod(0o640)
            expected_mode = path.stat().st_mode & 0o777
            self.assertTrue(is_text_path(path))
            snapshot = read_text_file(path)
            write_text_file(
                path, snapshot.encode("VAR=2\n"), expected=snapshot.original
            )
            self.assertEqual(path.read_bytes(), b"VAR=2\r\n")
            self.assertEqual(path.stat().st_mode & 0o777, expected_mode)
            with self.assertRaises(FileConflictError):
                write_text_file(path, b"bad", expected=snapshot.original)
            path.chmod(0o444)
            with self.assertRaises(PermissionError):
                write_text_file(path, b"bad", expected=path.read_bytes())
            path.chmod(0o640)
            path.unlink()
            with self.assertRaises(FileConflictError):
                write_text_file(path, b"bad", expected=b"old")
            with self.assertRaises(FileNotFoundError):
                read_text_file(path)
            self.assertFalse(list(Path(folder).iterdir()))

    def test_bom_detected_before_nulls_and_unencodable_output_rejected(self):
        for codec, bom in [
            ("utf-16-le", codecs.BOM_UTF16_LE),
            ("utf-32-le", codecs.BOM_UTF32_LE),
        ]:
            data = bom + "hello".encode(codec)
            self.assertEqual(decode_bytes(data).encode("hello"), data)
        with self.assertRaises(UnicodeError):
            decode_bytes(b"abc").encode("😀", encoding="cp1252")

    def test_unicode_paragraph_separators_survive_the_qt_normalized_model(self):
        for separator in ("\u2028", "\u2029"):
            original = ("one" + separator + "two").encode()
            snapshot = decode_bytes(original)
            self.assertEqual(snapshot.text, "one\ntwo")
            self.assertEqual(snapshot.encode(snapshot.text), original)
            self.assertEqual(
                snapshot.encode("one\nchanged"),
                ("one" + separator + "changed").encode(),
            )

    def test_explicit_bom_removal_and_utf16_conversion(self):
        snapshot = decode_bytes(codecs.BOM_UTF8 + b"hello")
        self.assertEqual(snapshot.encode("hello", bom=b""), b"hello")
        converted = snapshot.encode("hello", encoding="utf-16-le")
        self.assertTrue(converted.startswith(codecs.BOM_UTF16_LE))
        self.assertEqual(decode_bytes(converted).text, "hello")
