"""Cache-backed filename search for explicitly admitted local resource providers.

Provider entry/guard checks remain authoritative over cached metadata. The caller
must opt in physical local adapters; private and session-only providers stay in RAM.
"""
from contextlib import closing
from datetime import datetime
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

    def cached(self, provider, directory, query, *, cancelled=lambda: False, progress=None):
        """Publish provisional names without per-hit I/O; actions must revalidate.

        Only explicitly admitted ordinary providers can use this display path.
        The storage root/scope is still checked before publishing each batch.
        None means there is no saved snapshot, and never starts an index build.
        """
        if not self.supports(provider):
            return None
        directory = provider.relative(directory)
        folder = provider._locate(directory)
        from ..filesystem.local_access import check_local_path
        check_local_path(folder, recursive=True)
        snapshot = self.cache.peek(folder, cancelled=cancelled)
        if snapshot is None:
            return None
        with snapshot, closing(snapshot.iter_search(query, cancelled=cancelled)) as matches:
            rows, last_report, published = [], None, -1

            def report(*, finished=False):
                nonlocal last_report, published
                check_cancelled(cancelled)
                now = monotonic()
                publish = progress is not None and len(rows) != published and (
                    finished or last_report is None or now - last_report >= .25)
                if publish or finished:
                    provider._guard(folder)
                    check_cancelled(cancelled)
                if publish:
                    progress(SearchResult(list(rows), 0, False, [], cached=True))
                    last_report, published = now, len(rows)

            while page := tuple(islice(matches, 50)):
                for entry in page:
                    check_cancelled(cancelled)
                    if entry.symlink:
                        continue
                    # Both paths are lexical: cached metadata authorizes display
                    # only, never opening a file or following a replaced link.
                    name = entry.path.relative_to(folder).as_posix()
                    path = provider.relative(entry.path.relative_to(provider.root).as_posix())
                    rows.append(dict(name=name, path=path, directory=entry.directory,
                        size=entry.size, cached=True, hidden=entry.path.name.startswith('.'),
                        modified=datetime.fromtimestamp(entry.modified_ns / 1e9).astimezone().isoformat(
                            sep=' ', timespec='seconds')))
                report()
            report(finished=True)
            return SearchResult(rows, 0, False, [], cached=True)

    def search(self, provider, directory, query, *, cancelled=lambda: False, progress=None,
               cached_progress=False):
        if not self.supports(provider):
            return search_resources(provider, directory, query, cancelled=cancelled, progress=progress)
        try:
            if cached_progress and progress is not None:
                saved = self.cached(provider, directory, query, cancelled=cancelled, progress=progress)
                if saved is not None:
                    # Keep the full cached list until validation is complete;
                    # a growing validated prefix would make it shrink/flicker.
                    progress = None
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
            last_report, checked, reported = monotonic(), 0, False

            def report(*, page_end=False):
                nonlocal last_report, reported
                if progress is None or not rows:
                    return
                now = monotonic()
                if ((not reported and (page_end or now - last_report >= .05))
                        or (reported and now - last_report >= .25)):
                    provider._guard(folder)
                    check_cancelled(cancelled)
                    progress(SearchResult(list(rows), checked, False, list(errors)))
                    last_report, reported = now, True

            while True:
                # Keep both SQL mapping and provider admission bounded before
                # the first publication. The snapshot pins paging/order while
                # another worker refreshes the durable index.
                page = tuple(islice(matches, 50))
                if not page:
                    break
                for entry in page:
                    # Publish before another potentially slow admission, even
                    # when the preceding hit was missing or inaccessible.
                    report()
                    check_cancelled(cancelled)
                    checked += 1
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
                report(page_end=True)
            provider._guard(folder)
            check_cancelled(cancelled)
            return SearchResult(rows, len(snapshot.entries), snapshot.complete and not errors, errors)
