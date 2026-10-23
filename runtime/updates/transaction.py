"""Stdlib-only update transactions and detached apply/restart runner.

Hosts own channels, repositories, protected paths, UI, and shutdown approval.
This file is copied outside the installation before an application exits.
"""
import argparse
from contextlib import contextmanager, nullcontext
import fnmatch
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time
from tempfile import NamedTemporaryFile

MARKER = '.app-install.json'


class RollbackError(RuntimeError):
    """Recovery needs intervention; do not relaunch a partially restored app."""


def relative(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value or ':' in value:
        raise ValueError('Update paths must be relative')
    return Path(*path.parts)


def contained(root, name):
    path = root / relative(name)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Update path escapes installation: {name}')
    for part in (path, *path.parents):
        if part == root.parent:
            break
        if part != path and part.is_file():
            raise ValueError(f'Update destination parent is not a directory: {name}')
        if part.is_symlink():
            raise ValueError(f'Update path uses a symbolic link: {name}')
    return path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def git(root, *args, allowed=(0,)):
    result = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-C', str(root), *args],
                            stdin=subprocess.DEVNULL, capture_output=True, timeout=180)
    if result.returncode not in allowed:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip() or 'Git update operation failed')
    return result


def head(root):
    return git(root, 'rev-parse', 'HEAD').stdout.decode().strip()


def ignored(root, name, protected):
    # Always preserve the host's private roots, even if remote ignore rules change.
    path = PurePosixPath(name)
    if any(fnmatch.fnmatchcase(part, pattern) for part in path.parts for pattern in protected):
        return True
    # Conservative archive-mode protection: positive ignore rules remain protected;
    # negated rules never remove protection. Git mode also uses Git's own matcher.
    for parent in (root, *(root / Path(*path.parts[:i]) for i in range(1, len(path.parts)))):
        ignore = parent / '.gitignore'
        if not ignore.is_file() or ignore.is_symlink():
            continue
        sub = (root / Path(*path.parts)).relative_to(parent).as_posix()
        for line in ignore.read_text(encoding='utf-8', errors='replace').splitlines():
            rule = line.strip()
            if not rule or rule.startswith(('#', '!')):
                continue
            rule = rule.strip('/')
            if ('/' not in rule and any(fnmatch.fnmatchcase(part, rule) for part in PurePosixPath(sub).parts)
                    or fnmatch.fnmatchcase(sub, rule) or sub.startswith(rule + '/')):
                return True
    return False


def clean(root):
    if git(root, 'status', '--porcelain', '--untracked-files=no', '--ignore-submodules=all').stdout:
        raise ValueError(f'Uncommitted tracked changes in {root}; save or commit them before updating')
    git_dir = Path(git(root, 'rev-parse', '--absolute-git-dir').stdout.decode().strip())
    if any((git_dir / name).exists() for name in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'rebase-merge', 'rebase-apply')):
        raise ValueError('Finish the active Git operation before updating')


def gitlinks(root, revision):
    links = {}
    for record in git(root, 'ls-tree', '-r', '-z', revision).stdout.split(b'\0'):
        if not record:
            continue
        identity, name = record.split(b'\t', 1)
        mode, kind, commit = identity.split()
        if mode == b'160000':
            links[os.fsdecode(name)] = commit.decode()
    return links


def protect_git(root, revision, protected):
    names = [os.fsdecode(name) for name in git(root, 'ls-tree', '-r', '--name-only', '-z', revision).stdout.split(b'\0') if name]
    # A checkout can delete old tracked private files too, so protect both trees.
    names = sorted(set(names) | {os.fsdecode(name) for name in git(root, 'ls-files', '-z').stdout.split(b'\0') if name})
    private = set()
    for flags in (('--others', '--exclude-standard'), ('--others', '--ignored', '--exclude-standard')):
        private.update(os.fsdecode(name) for name in git(root, 'ls-files', '-z', *flags).stdout.split(b'\0') if name)
    ignored_targets = b''
    if names:
        # check-ignore needs stdin; keep all names separate without shell quoting.
        result = subprocess.run(['git', '-C', str(root), 'check-ignore', '--no-index', '-z', '--stdin'],
                                input=b'\0'.join(os.fsencode(name) for name in names) + b'\0',
                                capture_output=True, timeout=30)
        if result.returncode not in (0, 1):
            raise RuntimeError('Could not check ignored update paths')
        ignored_targets = result.stdout
    if ignored_targets:
        raise ValueError('The update includes paths ignored by this installation')
    for name in names:
        if ignored(root, name, protected):
            raise ValueError(f'Update would replace a protected path: {name}')
        for existing in private:
            if name == existing or existing.startswith(name + '/') or name.startswith(existing + '/'):
                raise ValueError(f'Update would overwrite a local file: {existing}')


def prepare_git(root, revision, protected, remote=None):
    if not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Expected a pinned commit for Git updates')
    if remote is not None and (not isinstance(remote, str) or remote.startswith('-')):
        raise ValueError('Invalid Git update source')
    root = root.resolve()
    plans = []
    def visit(directory, target, source=None):
        clean(directory)
        before = head(directory)
        if source is not None:
            git(directory, 'fetch', '--no-tags', '--recurse-submodules=no', source, target)
        elif git(directory, 'cat-file', '-e', target + '^{commit}', allowed=(0, 128)).returncode:
            git(directory, 'fetch', '--no-tags', '--recurse-submodules=no', 'origin', target)
        old_links, new_links = gitlinks(directory, before), gitlinks(directory, target)
        if set(old_links) != set(new_links):
            raise ValueError('Submodule layout changed; this update requires a manual Git update')
        protect_git(directory, target, protected)
        branch = git(directory, 'symbolic-ref', '--quiet', '--short', 'HEAD', allowed=(0, 1)).stdout.decode().strip()
        plans.append({'root': str(directory), 'before': before, 'target': target, 'branch': branch})
        for name, commit in new_links.items():
            child = contained(directory, name)
            if not (child / '.git').exists():
                raise ValueError(f'Initialize submodule {name} before updating')
            # A locally selected submodule revision is a local modification too.
            if head(child) != old_links[name]:
                raise ValueError(f'Submodule {name} differs from its installed pin')
            visit(child, commit)
    visit(root, revision, remote)
    return {'kind': 'git', 'root': str(root), 'repos': plans, 'protected': list(protected)}


def apply_git(plan):
    repos, protected = plan['repos'], plan['protected']
    for entry in repos:
        root = Path(entry['root'])
        if head(root) != entry['before']:
            raise ValueError('Installation changed after update preparation')
        clean(root)
        protect_git(root, entry['target'], protected)
    changed = []
    try:
        for entry in repos:
            # Never use force, reset --hard, clean, or overwrite ignored files.
            changed.append(entry)
            git(Path(entry['root']), 'checkout', '--no-overwrite-ignore', '--detach', entry['target'])
    except BaseException:
        try:
            for entry in reversed(changed):
                root = Path(entry['root'])
                git(root, 'checkout', '--no-overwrite-ignore', '--detach', entry['before'])
                if entry['branch'] and git(root, 'rev-parse', entry['branch']).stdout.decode().strip() == entry['before']:
                    git(root, 'checkout', '--no-overwrite-ignore', entry['branch'])
        except Exception as recovery:
            raise RollbackError(f'Git rollback failed: {recovery}') from recovery
        raise


def prepare_archive(root, snapshot, revision, protected):
    root, snapshot = root.resolve(), snapshot.resolve()
    marker = contained(root, MARKER)
    installed = json.loads(marker.read_text(encoding='utf-8'))
    if installed.get('format') != 1 or not isinstance(installed.get('files'), dict):
        raise ValueError('This installation has no valid managed-file manifest')
    files = {path.relative_to(snapshot).as_posix(): digest(contained(snapshot, path.relative_to(snapshot).as_posix()))
             for path in snapshot.rglob('*') if path.is_file()}
    for name, expected in installed['files'].items():
        path = contained(root, name)
        if ignored(root, name, protected):
            raise ValueError(f'Installed manifest contains a protected path: {name}')
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f'Locally modified managed file: {name}; preserve your edits before updating')
    for name in files:
        target = contained(root, name)
        if ignored(root, name, protected):
            raise ValueError(f'Update includes a protected/ignored path: {name}')
        if target.exists() and name not in installed['files']:
            raise ValueError(f'Update would overwrite an unmanaged file: {name}')
    return {'kind': 'archive', 'root': str(root), 'snapshot': str(snapshot), 'revision': revision,
            'previous': installed, 'files': files, 'protected': list(protected), 'marker_hash': digest(marker)}


def _archive_target(root, name, expected):
    """Recheck the installed bytes immediately before a planned mutation."""
    target = contained(root, name)
    if (expected is not None and (not target.is_file() or digest(target) != expected)
            or expected is None and target.exists()):
        raise ValueError(f'Local file changed during update: {name}')
    return target


@contextmanager
def _staged_update(target):
    """Own a private sibling until verified publication or failed-copy cleanup."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(prefix='.' + target.name + '.update-', dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        yield temporary
    finally:
        temporary.unlink(missing_ok=True)


def apply_archive(plan, workspace):
    root, snapshot = Path(plan['root']), Path(plan['snapshot'])
    # Recheck all local files after shutdown, including edits made during preparation.
    current = prepare_archive(root, snapshot, plan['revision'], plan['protected'])
    if current['previous'] != plan['previous'] or current['marker_hash'] != plan['marker_hash'] or current['files'] != plan['files']:
        raise ValueError('Installation or staged update changed after preparation')
    names = set(plan['previous']['files']) | set(plan['files']) | {MARKER}
    backup = workspace / 'rollback'
    backup.mkdir()
    existed = {}
    changed = {}
    try:
        # The manifest advertises the revision only after every managed file.
        for name in [*sorted(names - {MARKER}), MARKER]:
            expected = plan['marker_hash'] if name == MARKER else plan['previous']['files'].get(name)
            target = _archive_target(root, name, expected)
            saved = backup / relative(name)
            existed[name] = target.is_file()
            if existed[name]:
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
                if digest(saved) != expected:
                    raise ValueError(f'Recovery copy failed verification: {name}')
            staging = _staged_update(target) if name in plan['files'] or name == MARKER else nullcontext(None)
            with staging as temporary:
                if name in plan['files']:
                    shutil.copy2(snapshot / relative(name), temporary)
                    if digest(temporary) != plan['files'][name]:
                        raise ValueError('Staged file changed during update')
                elif name == MARKER:
                    temporary.write_text(json.dumps({'format': 1, 'revision': plan['revision'], 'files': plan['files']}, indent=2), encoding='utf-8')
                    shutil.copymode(target, temporary)
                published = digest(temporary) if name == MARKER else plan['files'].get(name)
                target = _archive_target(root, name, expected)
                (workspace / 'rollback.json').write_text(json.dumps({'root': str(root), 'files': existed}), encoding='utf-8')
                if temporary is not None:
                    temporary.replace(target)
                else:
                    target.unlink()
                changed[name] = published
    except BaseException:
        try:
            for name in reversed(changed):
                target = _archive_target(root, name, changed[name])
                if existed[name]:
                    expected = plan['marker_hash'] if name == MARKER else plan['previous']['files'][name]
                    with _staged_update(target) as temporary:
                        shutil.copy2(backup / relative(name), temporary)
                        if digest(temporary) != expected:
                            raise ValueError(f'Restored file failed verification: {name}')
                        target = _archive_target(root, name, changed[name])
                        temporary.replace(target)
                elif target.exists():
                    target.unlink()
        except Exception as recovery:
            raise RollbackError(f'File rollback failed: {recovery}') from recovery
        raise


def pid_alive(pid):
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def run_request(request_path):
    workspace = request_path.parent
    request = json.loads(request_path.read_text(encoding='utf-8'))
    status = Path(request['status'])
    deadline = time.monotonic() + 120
    while pid_alive(request['pid']):
        if time.monotonic() > deadline:
            status.parent.mkdir(parents=True, exist_ok=True)
            status.write_text(json.dumps({'success': False, 'message': 'The application did not exit; update was not applied',
                                          'recovery': str(workspace)}), encoding='utf-8')
            return 1
        time.sleep(.1)
    relaunch = True
    try:
        if request['plan']['kind'] == 'git':
            apply_git(request['plan'])
        else:
            apply_archive(request['plan'], workspace)
        outcome = {'success': True, 'message': 'Update installed.'}
    except Exception as error:
        outcome = {'success': False, 'message': str(error), 'recovery': str(workspace)}
        relaunch = not isinstance(error, RollbackError)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(json.dumps(outcome), encoding='utf-8')
    if relaunch:
        subprocess.Popen(request['restart'], cwd=request['plan']['root'], stdin=subprocess.DEVNULL,
                         start_new_session=os.name != 'nt', close_fds=True)
    return 0 if outcome['success'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path)
    args = parser.parse_args()
    raise SystemExit(run_request(args.request))
