"""Cache-backed filename search for explicitly admitted local resource providers.

Provider entry/guard checks remain authoritative over cached metadata. The caller
must opt in physical local adapters; private and session-only providers stay in RAM.
"""
from ..runtime.operations import check_cancelled
from .providers import SearchResult, search_resources


class IndexedLocalSearch:
    def __init__(self, database, *, eligible):
        from ..filesystem.index import DirectoryCache
        self.cache = DirectoryCache(database=database)
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
        with self.cache.get(folder, cancelled=cancelled, validate_files=False):
            check_cancelled(cancelled)
            provider._guard(folder)

    def search(self, provider, directory, query, *, cancelled=lambda: False, progress=None):
        if not self.supports(provider):
            return search_resources(provider, directory, query, cancelled=cancelled, progress=progress)
        directory = provider.relative(directory)
        folder = provider._locate(directory)
        from ..filesystem.local_access import check_local_path
        check_local_path(folder, recursive=True)
        snapshot = self.cache.peek(folder, cancelled=cancelled)
        if snapshot is None:
            snapshot = self.cache.get(folder, cancelled=cancelled, validate_files=False)
        with snapshot:
            rows, errors = [], [(str(path), error) for path, error in snapshot.errors]
            for entry in snapshot.search(query, cancelled=cancelled):
                check_cancelled(cancelled)
                if entry.symlink:
                    continue
                try:
                    # Recheck the provider boundary and revision before publishing
                    # a cached hit; saved names are never authority to open files.
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
            return SearchResult(rows, len(snapshot.entries), snapshot.complete and not errors, errors)
