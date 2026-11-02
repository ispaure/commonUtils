"""Cancellable name and optional document-text searches over rooted providers."""
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


def search_resources(provider, directory, query, *, cancelled=lambda: False, max_entries=None, progress=None,
                     list_children=None, read_text=None):
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
    def collect(row, path):
        name = row['name']
        by_name = matches_name(name, terms)
        if not by_name:
            if read_text is None or row['directory']:
                return
            missing = [term for term in terms if not matches_name(name, (term,))]
            try:
                body = read_text(path, cancelled=cancelled)
            except (OSError, ValueError) as error:
                errors.append((path, str(error)))
                return
            if not matches_name(body, missing):
                return
        item = dict(row)
        item['name'] = path[len(directory) + 1:] if directory else path
        if read_text is not None:
            item['content_match'] = not by_name
        rows.append(item)

    scope = getattr(provider, 'operation', None)
    with scope(cancelled) if scope else nullcontext():
        recursive = getattr(provider, 'search_entries', None)
        if recursive is not None and list_children is None:
            for row in recursive(directory, cancelled=cancelled):
                check_cancelled(cancelled)
                path = provider.relative(row['path'])
                if not path or path == directory or (directory and not path.startswith(directory + '/')):
                    raise ValueError('Search provider returned an entry outside its folder.')
                if max_entries is not None and scanned >= max_entries:
                    return SearchResult(rows, scanned, False, errors)
                scanned += 1
                collect(row, path)
                report()
            return SearchResult(rows, scanned, not errors, errors)
        while queue:
            check_cancelled(cancelled)
            folder = queue.popleft()
            if folder in visited:
                continue
            visited.add(folder)
            try:
                children = (list_children or provider.list)(folder, cancelled=cancelled)
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
                collect(row, path)
                if row['directory']:
                    queue.append(path)
                report()
    return SearchResult(rows, scanned, not errors, errors)
