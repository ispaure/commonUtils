"""Content manifests and streamed member replacement for open ZIP adapters."""
from hashlib import sha256
import zipfile
from ..runtime.operations import check_cancelled
from ..runtime.streams import iter_chunks, stream_signature
from dataclasses import dataclass
from .members import copy_member_info


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


@dataclass(frozen=True)
class MemberOperation:
    name: str
    info: object = None
    data: bytes | None = None
    stored: bool = False


def member_plan(original, replacements, *, include=None, first=(), stored=()):
    """Capture ordered retain/replace/add operations; excluded members are removed."""
    ranks = {name: index for index, name in enumerate(first)}
    members = sorted(original.infolist(), key=lambda info: ranks.get(info.filename, len(ranks)))
    planned = set()
    for info in members:
        name = info.filename
        if include is not None and name not in include:
            continue
        planned.add(name)
        yield MemberOperation(name, info, replacements.get(name), name in stored)
    for name, data in replacements.items():
        if name not in planned:
            yield MemberOperation(name, data=data, stored=name in stored)


def write_members(original, output, plan, *, max_member_bytes=None,
                  cancelled=lambda: False, progress=None):
    """Stream one operation plan; encryption and publication belong to the caller."""
    expected = {}
    for operation in plan:
        check_cancelled(cancelled)
        name, info, data = operation.name, operation.info, operation.data
        if progress:
            progress(0, 0, f'Rebuilding {name}')
        target = copy_member_info(info, output) if info is not None else name
        if info is not None and operation.stored:
            target.compress_type = zipfile.ZIP_STORED
        if data is not None:
            if info is None:
                output.writestr(target, data, compress_type=zipfile.ZIP_STORED if operation.stored else zipfile.ZIP_DEFLATED)
            else:
                output.writestr(target, data)
            expected[name] = len(data), sha256(data).hexdigest()
        elif info.is_dir():
            output.writestr(target, b'')
            expected[name] = None
        else:
            if max_member_bytes is not None and info.file_size > max_member_bytes:
                raise ValueError('Archive member exceeds the processing limit.')
            digest, length = sha256(), 0
            with original.open(info) as incoming, output.open(target, 'w', force_zip64=True) as outgoing:
                for chunk in iter_chunks(incoming, cancelled=cancelled):
                    length += len(chunk)
                    if max_member_bytes is not None and length > max_member_bytes:
                        raise ValueError('Archive member exceeds the processing limit.')
                    outgoing.write(chunk)
                    digest.update(chunk)
            expected[name] = length, digest.hexdigest()
    return expected


def rewrite_members(original, output, replacements, *, first=(), stored=(),
                    max_member_bytes=None, cancelled=lambda: False,
                    include=None, preserve_comment=True, progress=None):
    """Plan and stream replacements/additions with optional retained-member selection."""
    if preserve_comment:
        output.comment = original.comment
    return write_members(original, output,
                         member_plan(original, replacements, include=include, first=first, stored=stored),
                         max_member_bytes=max_member_bytes, cancelled=cancelled, progress=progress)
