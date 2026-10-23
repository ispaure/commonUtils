"""Cancellable, bounded name searches over rooted providers; results stay in RAM."""
from collections import deque
from contextlib import nullcontext
from dataclasses import dataclass
from time import monotonic
from ..runtime.operations import check_cancelled
from .names import search_terms, matches_name


@dataclass
class SearchResult:
    rows: list
    scanned: int
    complete: bool
    errors: list


def search_resources(provider, directory, query, *, cancelled=lambda: False, max_entries=None, progress=None):
    directory = provider.relative(directory)
    terms = search_terms(query)
    queue, visited, rows, errors = deque([directory]), set(), [], []
    scanned = 0
    reported = False
    last_report = monotonic()
    def report():
        nonlocal reported, last_report
        now = monotonic()
        if progress is not None and ((rows and not reported) or now - last_report >= .25):
            # A detached snapshot can cross the worker/UI boundary while the
            # breadth-first scan continues through unrelated, slower folders.
            progress(SearchResult(list(rows), scanned, False, list(errors)))
            reported = bool(rows)
            last_report = now
    scope = getattr(provider, 'operation', None)
    with scope(cancelled) if scope else nullcontext():
        recursive = getattr(provider, 'search_entries', None)
        if recursive is not None:
            for row in recursive(directory, cancelled=cancelled):
                check_cancelled(cancelled)
                path = provider.relative(row['path'])
                if not path or path == directory or (directory and not path.startswith(directory + '/')):
                    raise ValueError('Search provider returned an entry outside its folder.')
                if max_entries is not None and scanned >= max_entries:
                    return SearchResult(rows, scanned, False, errors)
                scanned += 1
                if matches_name(row['name'], terms):
                    item = dict(row)
                    item['name'] = path[len(directory) + 1:] if directory else path
                    rows.append(item)
                report()
            return SearchResult(rows, scanned, True, errors)
        while queue:
            check_cancelled(cancelled)
            folder = queue.popleft()
            if folder in visited:
                continue
            visited.add(folder)
            try:
                children = provider.list(folder, cancelled=cancelled)
            except OSError as error:
                errors.append((folder, str(error)))
                continue
            for row in children:
                check_cancelled(cancelled)
                path = provider.relative(row['path'])
                if path.rpartition('/')[0] != folder or path == folder:
                    raise ValueError('Search provider returned an entry outside its folder.')
                if max_entries is not None and scanned >= max_entries:
                    return SearchResult(rows, scanned, False, errors)
                scanned += 1
                if matches_name(row['name'], terms):
                    item = dict(row)
                    # Show the relative location to distinguish equal names in subfolders.
                    item['name'] = path[len(directory) + 1:] if directory else path
                    rows.append(item)
                if row['directory']:
                    queue.append(path)
                report()
    return SearchResult(rows, scanned, not errors, errors)
