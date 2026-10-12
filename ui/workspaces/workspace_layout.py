"""Rebuild a dock split from its visible partition, retaining every tab group.

Qt splitDockWidget tabifies instead of splitting an anchor which still belongs
to a native tab group (including some singleton groups). Capture the spatial
partition before removing docks, split its leaves, then restore tabification.
"""
from .. import pyside as qt


def split_at(workspace, moving, anchor, side):
    groups = []
    seen = set()
    for dock in workspace.docks:
        if dock in seen or dock.isFloating():
            continue
        connected = {dock, *workspace.tabifiedDockWidgets(dock)}
        members = [item for item in workspace.docks if item in connected]
        for bar in workspace.findChildren(qt.QTabBar):
            if bar.parent() is workspace:
                ordered = [workspace._tab_dock(bar, index) for index in range(bar.count())]
                if set(ordered) == connected:
                    members = ordered
                    break
        seen.update(members)
        visible = next((item for item in members if workspace.rect().intersects(item.geometry())), dock)
        rect = qt.QRect(visible.geometry())
        members = [item for item in members if item is not moving]
        if members:
            groups.append(dict(members=members, active=visible if visible in members else members[0], rect=rect))
    target = next(group for group in groups if anchor in group['members'])

    def partition(items):
        if len(items) == 1:
            return items[0]
        for orientation in (qt.Qt.Orientation.Horizontal, qt.Qt.Orientation.Vertical):
            horizontal = orientation == qt.Qt.Orientation.Horizontal
            ordered = sorted(items, key=lambda item: item['rect'].left() if horizontal else item['rect'].top())
            for index in range(1, len(ordered)):
                end = max(item['rect'].right() if horizontal else item['rect'].bottom() for item in ordered[:index])
                start = min(item['rect'].left() if horizontal else item['rect'].top() for item in ordered[index:])
                if end < start:
                    return dict(axis=orientation, children=[partition(ordered[:index]), partition(ordered[index:])])
        # Hidden/programmatically constructed containers may not yet have useful
        # coordinates. Retain their stable registration order until first layout.
        return dict(axis=qt.Qt.Orientation.Horizontal, children=items)

    tree = partition(groups)
    original = dict(target)
    rect = target['rect']
    left = qt.QRect(rect.left(), rect.top(), max(1, rect.width() // 2), rect.height())
    right = qt.QRect(left.right() + 1, rect.top(), max(1, rect.width() - left.width()), rect.height())
    original['rect'] = right if side == 'left' else left
    new = dict(members=[moving], active=moving, rect=left if side == 'left' else right)
    target.clear()
    target.update(axis=qt.Qt.Orientation.Horizontal, children=[new, original] if side == 'left' else [original, new])

    def normalize(node):
        if 'members' in node:
            return node
        children = [normalize(child) for child in node['children']]
        node['children'] = [part for child in children
                            for part in (child['children'] if child.get('axis') == node['axis'] else [child])]
        return node

    tree = normalize(tree)

    def leaves(node):
        if 'members' in node:
            return [node]
        return [leaf for child in node['children'] for leaf in leaves(child)]

    all_leaves = leaves(tree)
    for leaf in all_leaves:
        for dock in leaf['members']:
            workspace.removeDockWidget(dock)
    workspace.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, all_leaves[0]['members'][0])
    all_leaves[0]['members'][0].show()

    def build(node):
        if 'members' in node:
            return
        children = node['children']
        representatives = [leaves(child)[0]['members'][0] for child in children]
        for first, second in zip(representatives, representatives[1:]):
            workspace.splitDockWidget(first, second, node['axis'])
            second.show()
        for child in children:
            build(child)
        sizes = []
        for child in children:
            rectangles = [leaf['rect'] for leaf in leaves(child)]
            extent = qt.QRect(rectangles[0])
            for rectangle in rectangles[1:]:
                extent = extent.united(rectangle)
            sizes.append(max(1, extent.width() if node['axis'] == qt.Qt.Orientation.Horizontal else extent.height()))
        workspace.resizeDocks(representatives, sizes, node['axis'])

    build(tree)
    for leaf in all_leaves:
        active = leaf['active']
        first = leaf['members'][0]
        for dock in leaf['members']:
            if dock is not first:
                workspace.tabifyDockWidget(first, dock)
            dock.show()
        active.raise_()
