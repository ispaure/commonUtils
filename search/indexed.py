"""Cache-backed filename search for explicitly admitted local resource providers.

Provider entry/guard checks remain authoritative over cached metadata. The caller
must opt in physical local adapters; private and session-only providers stay in RAM.
"""
from contextlib import closing
from itertools import islice
from sqlite3 import Error as DatabaseError
from time import monotonic

from ..filesystem.index.coordinator import IndexUnavailableError
from ..runtime.operations import check_cancelled
from .providers import SearchResult, search_resources


class IndexedLocalSearch:
    def __init__(self, database, *, eligible, cache=None):
        from ..filesystem.index import DirectoryCache
        self.cache = cache if cache is not None else DirectoryCache(database=database)
        self.eligible = eligible

    def supports(self, provider):
        return (self.eligible(provider) and not provider.private
                and not getattr(provider, 'session_only', False)
                and not getattr(provider, 'remote_storage', False))

    def prepare(self, provider, directory, *, cancelled):
        if not self.supports(provider):
            return
        folder = provider._locate(directory)
        from ..filesystem.local_access import check_local_path
        check_local_path(folder, recursive=True)
        with self._prepare(folder, cancelled):
            check_cancelled(cancelled)
            provider._guard(folder)

    def _prepare(self, folder, cancelled):
        coordinator = self.cache.coordinator
        if coordinator is not None:
            return coordinator.prepare_search(folder, cancelled=cancelled)
        return self.cache.get(folder, cancelled=cancelled, validate_files=False)

    def search(self, provider, directory, query, *, cancelled=lambda: False, progress=None):
        if not self.supports(provider):
            return search_resources(provider, directory, query, cancelled=cancelled, progress=progress)
        try:
            return self._search(provider, directory, query, cancelled=cancelled, progress=progress)
        except (DatabaseError, IndexUnavailableError):
            # An unavailable disposable index must not disable provider search.
            # Keep repair/writer ownership separate from this read fallback.
            check_cancelled(cancelled)
            return search_resources(provider, directory, query, cancelled=cancelled, progress=progress)

    def _search(self, provider, directory, query, *, cancelled, progress):
        directory = provider.relative(directory)
        folder = provider._locate(directory)
        from ..filesystem.local_access import check_local_path
        check_local_path(folder, recursive=True)
        snapshot = self.cache.peek(folder, cancelled=cancelled)
        if snapshot is None:
            snapshot = self._prepare(folder, cancelled)
        with snapshot, closing(snapshot.iter_search(query, cancelled=cancelled)) as matches:
            rows, errors = [], [(str(path), error) for path, error in snapshot.errors]
            last_report, checked = None, 0
            while True:
                # Keep both SQL mapping and provider admission bounded before
                # the first publication. The snapshot pins paging/order while
                # another worker refreshes the durable index.
                page = tuple(islice(matches, 50))
                if not page:
                    break
                checked += len(page)
                for entry in page:
                    check_cancelled(cancelled)
                    if entry.symlink:
                        continue
                    try:
                        # Saved names are never authority to open files.
                        path = entry.path.relative_to(provider.root).as_posix()
                        row = provider.entry(path)
                    except FileNotFoundError:
                        continue
                    except (OSError, ValueError) as error:
                        errors.append((str(entry.path), str(error)))
                        continue
                    row['name'] = entry.path.relative_to(folder).as_posix()
                    rows.append(row)
                provider._guard(folder)
                check_cancelled(cancelled)
                now = monotonic()
                if progress is not None and rows and (last_report is None or now-last_report >= .25):
                    progress(SearchResult(list(rows), checked, False, list(errors)))
                    last_report = now
            provider._guard(folder)
            check_cancelled(cancelled)
            return SearchResult(rows, len(snapshot.entries), snapshot.complete and not errors, errors)
