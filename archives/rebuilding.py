"""Content manifests and streamed member replacement for open ZIP adapters."""
from hashlib import sha256
import zipfile
from ..runtime.operations import check_cancelled
from ..runtime.streams import iter_chunks, stream_signature
from .zip_access import copy_member_info


def content_manifest(archive, *, cancelled=lambda: False, progress=None):
    native = getattr(archive, 'content_manifest', None)
    if native is not None and progress is None:
        check_cancelled(cancelled)
        return native(cancelled=cancelled)
    result, done = {}, 0
    total = sum(info.file_size for info in archive.infolist())
    for info in archive.infolist():
        check_cancelled(cancelled)
        def advanced(size):
            nonlocal done
            done += size
            if progress:
                progress(done, total, f'Verifying {info.filename}')
        if info.is_dir():
            with archive.open(info) as stream:
                stream_signature(stream, cancelled=cancelled, progress=advanced)
            result[info.filename] = None
        else:
            with archive.open(info) as stream:
                result[info.filename] = stream_signature(stream, cancelled=cancelled, progress=advanced)
    return result


def patched_manifest(archive, replacements, *, cancelled=lambda: False):
    result = content_manifest(archive, cancelled=cancelled)
    result.update({name: (len(data), sha256(data).hexdigest()) for name, data in replacements.items()})
    return result


def rewrite_members(original, output, replacements, *, first=(), stored=(),
                    max_member_bytes=None, cancelled=lambda: False):
    """Copy unchanged members, replace/add named bytes, and return expected hashes.

    Hosts own input validation, encryption, format rules, final verification and
    publication. `first` orders named entries before others; `stored` selects
    uncompressed entries. Both are explicit names without format-specific meaning.
    """
    output.comment = original.comment
    expected = {}
    ranks = {name: index for index, name in enumerate(first)}
    members = sorted(original.infolist(), key=lambda info: ranks.get(info.filename, len(ranks)))
    for info in members:
        check_cancelled(cancelled)
        target = copy_member_info(info, output)
        if info.filename in stored:
            target.compress_type = zipfile.ZIP_STORED
        if info.filename in replacements:
            data = replacements[info.filename]
            output.writestr(target, data)
            expected[info.filename] = len(data), sha256(data).hexdigest()
        elif info.is_dir():
            output.writestr(target, b'')
            expected[info.filename] = None
        else:
            if max_member_bytes is not None and info.file_size > max_member_bytes:
                raise ValueError('Archive member exceeds the processing limit.')
            digest, length = sha256(), 0
            with original.open(info) as incoming, output.open(target, 'w') as outgoing:
                for chunk in iter_chunks(incoming, cancelled=cancelled):
                    outgoing.write(chunk)
                    digest.update(chunk)
                    length += len(chunk)
            expected[info.filename] = length, digest.hexdigest()
    for name, data in replacements.items():
        if name not in expected:
            check_cancelled(cancelled)
            output.writestr(name, data, compress_type=zipfile.ZIP_STORED if name in stored else zipfile.ZIP_DEFLATED)
            expected[name] = len(data), sha256(data).hexdigest()
    return expected
