"""Verified provider mutations, independent of storage encoding and UI."""
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from .paths import resource_path, resource_name
from .provider import require_capability, WritableDirectoryProvider
from ..operations import check_cancelled, MutationResult, MutationIncomplete
from ...persistence.publication import mutation_lock, save_transaction
from ...persistence.transfers import verify_unchanged, cleanup_published


def inventory(provider: WritableDirectoryProvider, path, *, cancelled=lambda: False):
    """Capture membership and versions before any destructive operation."""
    path = provider.relative(path)
    result = {}
    def visit(current, relative):
        check_cancelled(cancelled)
        if len(result) >= 10000 or relative.count('/') > 100:
            raise ValueError('Operation exceeds 10,000 entries or 100 folder levels.')
        row = provider.entry(current)
        result[relative] = row
        if row['directory']:
            for child in provider.list(current, cancelled=cancelled):
                name = resource_name(child['name'])
                visit('/'.join(p for p in (current, name) if p), '/'.join(p for p in (relative, name) if p))
    visit(path, '')
    return result


def delete_resource(provider: WritableDirectoryProvider, path, *, cancelled=lambda: False, expected=None):
    with mutation_lock:
        require_capability(provider, 'delete')
        if not provider.relative(path):
            raise ValueError('Cannot delete a storage root.')
        rows = inventory(provider, path, cancelled=cancelled)
        if expected is not None and rows != expected:
            raise ValueError('Source changed; nothing was deleted.')
        removed = []
        attempting = False
        try:
            for row in reversed(list(rows.values())):
                check_cancelled(cancelled)
                attempting = True
                provider.remove_empty(row['path'], row['revision'])
                removed.append(row['path'])
                attempting = False
        except Exception as error:
            state = 'partial' if removed else 'unchanged'
            if attempting:
                try:
                    provider.entry(row['path'])
                except FileNotFoundError:
                    removed.append(row['path'])
                    state = 'partial'
                except Exception:
                    state = 'unknown'
            if state != 'unchanged':
                raise MutationIncomplete('Deletion stopped after changing the source. Refresh to inspect the remaining items.',
                                         MutationResult(source_state=state, removed_paths=tuple(removed))) from error
            raise
        return MutationResult(source_state='removed', removed_paths=tuple(removed))


def _digest(provider, path, cancelled):
    digest = sha256()
    with provider.open(path) as stream:
        while chunk := stream.read(256 * 1024):
            check_cancelled(cancelled)
            digest.update(chunk)
    return digest.digest()


def move_resource(source: WritableDirectoryProvider, path, destination: WritableDirectoryProvider, target, *, cancelled=lambda: False):
    """Stage, verify, publish without overwriting, then remove unchanged source.

    A failure after publication can leave both copies; it never rolls back a
    verified destination. Cancellation during deletion can leave remaining source
    entries. No plaintext temporary file is required by this operation.
    """
    with mutation_lock:
        path, target = source.relative(path), destination.relative(target)
        if not path or not target:
            raise ValueError('Storage roots cannot be moved or replaced.')
        if source.storage_id == destination.storage_id:
            if source.storage_namespace != destination.storage_namespace:
                raise ValueError('Different provider views of the same storage cannot be moved directly.')
            require_capability(source, 'rename')
            require_capability(destination, 'rename')
            check_cancelled(cancelled)
            source.rename(path, target)
            return MutationResult(destination_published=True, source_state='removed')
        # Physical nesting is also unsafe across separately rooted local views.
        source_root, target_root = Path(source.storage_id), Path(destination.storage_id)
        if source_root == target_root or source_root in target_root.parents or target_root in source_root.parents:
            source_location = getattr(source, 'transfer_location', None)
            target_location = getattr(destination, 'transfer_location', None)
            if source_location is None or target_location is None:
                raise ValueError('Overlapping storage roots cannot be transferred.')
            directory = source.entry(path)['directory']
            origin = source_location(path, directory=directory)
            output = target_location(target, directory=directory)
            if origin == output or origin in output.parents or output in origin.parents:
                raise ValueError('Overlapping source and destination cannot be transferred.')
        require_capability(source, 'delete')
        require_capability(destination, 'create')
        require_capability(destination, 'rename')
        require_capability(destination, 'delete')
        rows = inventory(source, path, cancelled=cancelled)
        temporary = '/'.join(p for p in (target.rpartition('/')[0], '.transfer-' + uuid4().hex) if p)
        created = False
        try:
            for relative, row in rows.items():
                check_cancelled(cancelled)
                output = '/'.join(p for p in (temporary, relative) if p)
                if row['directory']:
                    destination.mkdir(output)
                else:
                    with source.open(row['path']) as stream:
                        destination.create_file(output, stream, cancelled=cancelled)
                    created = True
                    if _digest(source, row['path'], cancelled) != _digest(destination, output, cancelled):
                        raise ValueError('Destination verification failed; source preserved.')
                created = True
            verify_unchanged(rows, lambda: inventory(source, path, cancelled=cancelled),
                             message='Source changed during transfer; source preserved.')
            check_cancelled(cancelled)
            destination.rename(temporary, target)
            created = False
            result = cleanup_published(
                lambda: delete_resource(source, path, cancelled=cancelled, expected=rows),
                source_state=lambda: 'unchanged')
            return MutationResult(True, result.source_state, result.removed_paths)
        finally:
            if created:
                delete_resource(destination, temporary)


def save_resource_bytes(provider: WritableDirectoryProvider, path, data, *, expected_revision=None, cancelled=lambda: False):
    """Publish verified bytes as one operation; None means create, never overwrite."""
    from io import BytesIO
    with mutation_lock:
        require_capability(provider, 'create')
        require_capability(provider, 'delete')
        require_capability(provider, 'rename' if expected_revision is None else 'replace')
        path = provider.relative(path)
        if not path:
            raise ValueError('Choose a file name.')
        temporary = '/'.join(p for p in (path.rpartition('/')[0], '.save-' + uuid4().hex + Path(path).suffix) if p)
        created = False
        def stage():
            nonlocal created
            provider.create_file(temporary, BytesIO(data), cancelled=cancelled)
            created = True
        def verify():
            if _digest(provider, temporary, cancelled) != sha256(data).digest():
                raise ValueError('Saved content verification failed; original preserved.')
        def validate():
            if expected_revision is not None and provider.entry(path)['revision'] != expected_revision:
                raise ValueError('File changed; original preserved.')
        def publish():
            nonlocal created
            if expected_revision is None:
                provider.rename(temporary, path)
            else:
                provider.replace_created(temporary, path, expected_revision)
            created = False
        def cleanup():
            if created:
                delete_resource(provider, temporary)
        save_transaction(stage=stage, verify=verify, validate=validate,
                         publish=publish, cleanup=cleanup, cancelled=cancelled)


def save_resource_and_reopen(provider, path, data, *, reopen, expected_revision=None, cancelled=lambda: False):
    """Publish verified bytes, then prepare a host-owned replacement reader.

    The callback must reopen the destination and validate its contents. It runs
    without the save cancellation flag: once published, late cancellation cannot
    turn a completed save into an apparent no-op. Callers keep the old draft until
    this returns AND their UI handoff succeeds. Reader failure never rolls back a
    published destination; the structured error distinguishes it from save failure.
    """
    save_resource_bytes(provider, path, data, expected_revision=expected_revision, cancelled=cancelled)
    try:
        return reopen()
    except Exception as error:
        raise MutationIncomplete('The file was saved, but could not be reopened unchanged. Keep your draft and inspect the destination before retrying.',
                                 MutationResult(destination_published=True)) from error


def create_resource_folder(provider, path, *, cancelled=lambda: False):
    """Capability-checked folder creation, including cancellation before mutation."""
    with mutation_lock:
        require_capability(provider, 'create')
        check_cancelled(cancelled)
        provider.mkdir(provider.relative(path))
        return MutationResult(destination_published=True)


def rename_resource(provider, path, target, *, cancelled=lambda: False):
    return move_resource(provider, path, provider, target, cancelled=cancelled)
