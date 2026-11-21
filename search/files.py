"""Bounded text-file search over caller-supplied roots and buffer snapshots."""
from bisect import bisect_right
from contextlib import contextmanager
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
import os
import re
from sqlite3 import Error as DatabaseError
from ..persistence.text import read_text_file
from ..runtime.operations import OperationCancelled
from ..filesystem.links import is_junction


def _cached_walk(root, snapshot, cancelled):
    pending = [root]
    while pending and not cancelled():
        parent = pending.pop()
        if parent != root and (parent.is_symlink() or is_junction(parent)):
            continue
        try:
            children = snapshot.cached_child_names(parent, cancelled=cancelled)
        except (OSError, DatabaseError):
            children = None
        folders, files = [], []
        if children is not None:
            for name, directory, symlink in children:
                (folders if directory and not symlink else files).append(name)
        else:
            try:
                with os.scandir(parent) as children:
                    for entry in children:
                        if cancelled():
                            return
                        (folders if entry.is_dir() else files).append(entry.name)
            except OSError:
                continue
        # The caller prunes/sorts folders just as it does with os.walk.
        yield str(parent), folders, files
        pending.extend(parent / name for name in reversed(folders))


@contextmanager
def _file_tree(root, cache, cancelled):
    snapshot = None
    try:
        if cache is not None:
            from ..filesystem.local_access import check_local_path
            check_local_path(root, recursive=True)
            try:
                snapshot = cache.peek(root, cancelled=cancelled)
            except (OSError, DatabaseError):
                pass  # A disposable cache must not disable Find in Files.
        yield (_cached_walk(root, snapshot, cancelled) if snapshot is not None
               else os.walk(root, followlinks=False))
    finally:
        if snapshot is not None:
            snapshot.close()


@dataclass(frozen=True)
class SearchHit:
    path: Path
    line: int
    column: int
    start: int
    length: int
    excerpt: str
    excerpt_start: int
    excerpt_end: int


@dataclass(frozen=True)
class SearchResult:
    hits: tuple
    files: int
    limited: bool


def search_files(roots, excluded, query, masks='', *, case=False, whole=False,
                 regex=False, buffers=None, cancelled=lambda: False, limit=500,
                 max_files=10000, max_entries=100000, max_file_size=1024 * 1024,
                 cache=None, exclude_path=None, on_first_hit=None):
    """Search eligible files in order, optionally reporting the first hit on the caller's thread."""
    from .qt_text import find_matches
    if not query:
        return SearchResult((), 0, False)
    # Validate regex even when there are no eligible files.
    find_matches('', query, case=case, whole=whole, regex=regex, cancelled=cancelled)
    roots = tuple(Path(root).resolve() for root in roots)
    if exclude_path is not None:
        roots = tuple(root for root in roots if not exclude_path(root, root))
    buffers = buffers or {}
    patterns = [mask.strip().casefold() for mask in re.split('[;,]', masks) if mask.strip()]
    paths, visited = [], set()
    limited = False
    entries = 0
    def excluded_path(relative):
        return (any(part in excluded for part in relative.parts)
                or any(relative.as_posix() == name
                       or relative.as_posix().startswith(name.rstrip('/') + '/')
                       for name in excluded))
    def eligible(path, root):
        relative = path.relative_to(root)
        return (not excluded_path(relative)
                and (exclude_path is None or not exclude_path(path, root))
                and (not patterns or any(fnmatchcase(path.name.casefold(), pattern)
                     or fnmatchcase(relative.as_posix().casefold(), pattern) for pattern in patterns)))
    try:
        for root in roots:
            if not root.is_dir():
                raise ValueError(f'Search directory is unavailable: {root}')
            with _file_tree(root, cache, cancelled) as tree:
                for directory, folders, files in tree:
                    if cancelled():
                        return SearchResult((), 0, False)
                    parent = Path(directory)
                    folders[:] = sorted(name for name in folders if not (parent / name).is_symlink()
                                        and not is_junction(parent / name)
                                        and not excluded_path((parent / name).relative_to(root))
                                        and (exclude_path is None or not exclude_path(parent / name, root)))
                    entries += len(folders) + len(files)
                    for name in sorted(files):
                        path = parent / name
                        if path not in visited and not path.is_symlink() and eligible(path, root):
                            paths.append(path); visited.add(path)
                        if len(paths) >= max_files:
                            break
                    if len(paths) >= max_files or entries >= max_entries:
                        limited = True
                        break
            if limited:
                break
    except OperationCancelled:
        return SearchResult((), 0, False)
    for path in buffers:
        path = Path(path)
        if path not in visited and any(
                path.is_relative_to(root) and eligible(path, root)
                and (exclude_path is None or not any(
                    exclude_path(parent, root) for parent in path.parents if parent.is_relative_to(root)))
                for root in roots):
            if len(paths) >= max_files:
                limited = True
                break
            paths.append(path); visited.add(path)
    hits, matched_files = [], set()
    for path in paths:
        if cancelled():
            return SearchResult((), 0, False)
        try:
            if path in buffers:
                text = buffers[path]
                if len(text) > max_file_size:
                    continue
            else:
                if path.is_symlink() or path.stat().st_size > max_file_size:
                    continue
                text = read_text_file(path).text
        except (OSError, ValueError):
            continue
        matches, capped = find_matches(text, query, case=case, whole=whole, regex=regex, cancelled=cancelled)
        limited |= capped
        if not matches:
            continue
        lines = text.splitlines(keepends=True)
        starts = [0]
        for line in lines:
            starts.append(starts[-1] + len(line.encode('utf-16-le')) // 2)
        for match in matches:
            row = min(bisect_right(starts, match.start) - 1, len(lines))
            content = lines[row].rstrip('\r\n') if row < len(lines) else ''
            column = len(content.encode('utf-16-le')[:(match.start - starts[row]) * 2].decode('utf-16-le'))
            width = len(content.encode('utf-16-le')[(match.start - starts[row]) * 2:
                        (match.start - starts[row] + match.length) * 2].decode('utf-16-le'))
            left = max(0, column - 70)
            excerpt = content[left:left + 240]
            hit = SearchHit(path, row + 1, column, match.start, match.length,
                            excerpt, column - left, min(len(excerpt), column - left + width))
            if not hits and on_first_hit is not None:
                on_first_hit(hit)
            hits.append(hit)
            matched_files.add(path)
            if len(hits) >= limit:
                return SearchResult(tuple(hits), len(matched_files), True)
    return SearchResult(tuple(hits), len(matched_files), limited)


def preview_text(path, buffer=None):
    if buffer is not None:
        return buffer
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Preview is limited to files up to 1 MiB.')
    return read_text_file(path).text
