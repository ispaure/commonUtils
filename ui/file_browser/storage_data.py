"""Bounded storage graph collection, independent of Qt widget lifetime."""
from ...runtime.operations import check_cancelled


def collect_storage(cache, root, *, radial=False, metric='size', include_unknown=False, cancelled=lambda: False):
    snapshot = cache.peek(root, cancelled=cancelled)
    if snapshot is None:
        return [], {}, {}, False
    root_stats = snapshot.folder_stats([root], cancelled=cancelled).get(root)
    unknown = root_stats.disk_unknown if root_stats and metric == 'disk_size' else 0
    nodes, totals, root_entries = {}, {}, []
    known_totals = {}
    budget, queue = 3000, [root]
    for depth in range(1, 5 if radial else 2):
        if not queue or budget <= 0:
            break
        allowance = budget if depth == 4 or not radial else max(1, budget//(5-depth))
        next_queue = []
        for index, path in enumerate(queue):
            check_cancelled(cancelled)
            if allowance <= 0:
                break
            quota = max(1, allowance//(len(queue)-index)) if radial else budget
            source = snapshot
            children = source.storage_children(path, quota, cancelled=cancelled, metric=metric)
            if not children and path != root:
                source = cache.peek(path, cancelled=cancelled)
                children = source.storage_children(path, quota, cancelled=cancelled, metric=metric) if source else ()
            items = [(child, size) for child, directory, size in children]
            nodes[path] = items
            totals[path] = max(getattr(root_stats, metric) if path == root and root_stats else known_totals.get(path, 0), sum(size for _, size in items))
            if path == root:
                root_entries = items
            budget -= len(items)
            allowance -= len(items)
            next_queue.extend(child for child, directory, size in children if directory and size)
            known_totals.update({child: size for child, directory, size in children if directory})
        queue = next_queue
    result = root_entries, nodes, totals, snapshot.complete
    return result + (unknown,) if include_unknown else result
