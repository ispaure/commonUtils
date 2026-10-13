"""Cancellable, bounded name searches over rooted providers; results stay in RAM."""
from collections import deque
from contextlib import nullcontext
from dataclasses import dataclass
from .operations import check_cancelled


@dataclass
class SearchResult:
    rows: list
    scanned: int
    complete: bool
    errors: list


def search_resources(provider, directory, query, *, cancelled=lambda: False, max_entries=10000):
    directory = provider.relative(directory)
    query = query.strip().casefold()
    queue, visited, rows, errors = deque([directory]), set(), [], []
    scanned = 0
    scope = getattr(provider, 'operation', None)
    with scope(cancelled) if scope else nullcontext():
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
                if scanned >= max_entries:
                    return SearchResult(rows, scanned, False, errors)
                scanned += 1
                if query in row['name'].casefold():
                    item = dict(row)
                    # Show the relative location to distinguish equal names in subfolders.
                    item['name'] = path[len(directory) + 1:] if directory else path
                    rows.append(item)
                if row['directory']:
                    queue.append(path)
    return SearchResult(rows, scanned, not errors, errors)
