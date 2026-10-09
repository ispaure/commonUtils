"""Bounded text recognition and conflict-checked, lossless atomic text writes.

No Qt or application dependencies. Encodings are explicit when UTF detection is
ambiguous; legacy bytes are never silently replaced. Symlink targets are resolved
by callers so saving does not replace a link itself.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
import codecs
import os
from pathlib import Path
import re
import stat
from tempfile import NamedTemporaryFile

MAX_BYTES = 16 * 1024 * 1024
SIMPLE_BYTES = 1024 * 1024
BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
ENCODINGS = (
    "utf-8",
    "utf-8-sig",
    "utf-16-le",
    "utf-16-be",
    "utf-32-le",
    "cp1252",
    "latin-1",
)


class BinaryTextError(ValueError):
    pass


class FileConflictError(OSError):
    pass


def likely_binary(data):
    if any(data.startswith(bom) for bom, _ in BOMS):
        return False
    if b"\0" in data:
        return True
    return (
        bool(data)
        and sum(byte < 32 and byte not in (9, 10, 12, 13) for byte in data) / len(data)
        > 0.02
    )


def is_text_path(path):
    """Bounded sniff, suitable for activation; never enumerate or load whole files."""
    try:
        with Path(path).open("rb") as stream:
            return not likely_binary(stream.read(8192))
    except OSError:
        return False


def normalize(text):
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u2028", "\n")
        .replace("\u2029", "\n")
    )


@dataclass(frozen=True)
class TextSnapshot:
    path: Path | None
    original: bytes
    text: str
    encoding: str = "utf-8"
    bom: bytes = b""
    newline: str = "\n"
    disk_text: str = ""

    @property
    def digest(self):
        return sha256(self.original).digest()

    @property
    def mixed_endings(self):
        return len(set(re.findall(r"\r\n|\r|\n|\u2028|\u2029", self.disk_text))) > 1

    def encode(self, text, *, encoding=None, newline=None, bom=None):
        encoding = encoding or self.encoding
        if (
            encoding == self.encoding
            and newline is None
            and text == self.text
            and (bom is None or bom == self.bom)
        ):
            return self.original
        if newline is None and not self.mixed_endings:
            rendered = text.replace("\n", self.newline)
        elif newline is None:
            # Equal lines retain their own terminators, even in mixed files.
            source = self.disk_text.splitlines(keepends=True)
            destination = text.splitlines(keepends=True)
            endings = {}
            matcher = SequenceMatcher(
                None,
                [normalize(line) for line in source],
                destination,
                autojunk=len(source) > 2000,
            )
            for block in matcher.get_matching_blocks():
                for offset in range(block.size):
                    endings[block.b + offset] = source[block.a + offset]
            rendered = "".join(
                endings.get(index, line.replace("\n", self.newline))
                for index, line in enumerate(destination)
            )
        else:
            rendered = text.replace("\n", newline)
        if encoding == "utf-8-sig":
            return codecs.BOM_UTF8 + rendered.encode("utf-8")
        if bom is None:
            bom = (
                self.bom
                if encoding == self.encoding
                else next(
                    (
                        prefix
                        for prefix, codec in BOMS
                        if codec == encoding and codec != "utf-8"
                    ),
                    b"",
                )
            )
        return bom + rendered.encode(encoding, errors="strict")


def decode_bytes(data, *, path=None, encoding=None, force=False):
    if likely_binary(data) and not force:
        raise BinaryTextError(
            "This looks like a binary file. Use Force Open as Text only if intended."
        )
    bom = b""
    if encoding is None:
        for prefix, codec in BOMS:
            if data.startswith(prefix):
                bom, encoding = prefix, codec
                break
        encoding = encoding or ("latin-1" if force and likely_binary(data) else "utf-8")
    elif encoding == "utf-8-sig":
        encoding = "utf-8"
        bom = codecs.BOM_UTF8 if data.startswith(codecs.BOM_UTF8) else b""
    else:
        for prefix, codec in BOMS:
            if codec == encoding and data.startswith(prefix):
                bom = prefix
                break
    decoded = data[len(bom) :].decode(encoding, errors="strict")
    endings = re.findall(r"\r\n|\r|\n|\u2028|\u2029", decoded)
    newline = max(dict.fromkeys(endings), key=endings.count) if endings else "\n"
    return TextSnapshot(
        Path(path) if path else None,
        data,
        normalize(decoded),
        encoding,
        bom,
        newline,
        decoded,
    )


def read_text_file(path, *, encoding=None, force=False):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(
            "File exceeds the 16 MiB editing limit. Use a dedicated large-file viewer."
        )
    return decode_bytes(data, path=path, encoding=encoding, force=force)


def write_text_file(path, content, *, expected=None, allow_overwrite=False):
    """Write bytes atomically; retain source permissions and reject stale snapshots.

    Check both before staging and immediately before promotion. Arbitrary external
    processes cannot be made transactional with our rename; callers must still
    surface conflicts. No chmod of a read-only original is performed.
    """
    if len(content) > MAX_BYTES:
        raise ValueError("Encoded content exceeds the 16 MiB editing limit.")
    path = Path(path).resolve()

    def check():
        if path.exists():
            mode = path.stat().st_mode
            if not mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
                raise PermissionError(
                    "The file is read-only. Choose Save As to keep your changes."
                )
            if expected is None and not allow_overwrite:
                raise FileConflictError("The destination already exists.")
            if expected is not None:
                if path.stat().st_size != len(expected):
                    raise FileConflictError(
                        "The file changed on disk. Reload it or save your buffer elsewhere."
                    )
                with path.open("rb") as stream:
                    current = stream.read(len(expected) + 1)
                if sha256(current).digest() != sha256(expected).digest():
                    raise FileConflictError(
                        "The file changed on disk. Reload it or save your buffer elsewhere."
                    )
        elif expected is not None:
            raise FileConflictError(
                "The original file was deleted. Choose Save As to recover your buffer."
            )

    check()
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    staged = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            staged = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            staged.chmod(mode)
        check()
        if expected is None and not allow_overwrite:
            # Atomic no-clobber creation protects a racing new destination.
            os.link(staged, path)
            staged.unlink()
        else:
            os.replace(staged, path)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
