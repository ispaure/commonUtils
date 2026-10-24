"""Plan a dock partition before rebuilding Qt splits and restoring tab groups.

Qt splitDockWidget tabifies instead of splitting an anchor which still belongs
to a native tab group (including some singleton groups). Capture the spatial
partition before removing docks, split its leaves, then restore tabification.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from .. import pyside as qt


@dataclass(frozen=True)
class _TabGroup:
    members: tuple[qt.QDockWidget, ...]
    active: qt.QDockWidget
    rect: qt.QRect


@dataclass(frozen=True)
class _Split:
    axis: qt.Qt.Orientation
    children: tuple[_TabGroup | _Split, ...]


_Layout = _TabGroup | _Split


def split_at(workspace, moving, anchor, side):
    groups = _capture_groups(workspace, moving)
    target = next(group for group in groups if anchor in group.members)
    tree = _partition(groups)
    tree = _replace_group(tree, target, _split_group(target, moving, side))
    tree = _normalize(tree)
    _apply_layout(workspace, tree)


def _capture_groups(workspace, moving):
    """Capture native order/geometry, excluding the pane being repositioned."""
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
        members = tuple(item for item in members if item is not moving)
        if members:
            groups.append(_TabGroup(members, visible if visible in members else members[0], rect))
    return groups


def _partition(groups):
    """Infer horizontal/vertical partitions without mutating live docks."""
    if len(groups) == 1:
        return groups[0]
    for orientation in (qt.Qt.Orientation.Horizontal, qt.Qt.Orientation.Vertical):
        horizontal = orientation == qt.Qt.Orientation.Horizontal
        ordered = sorted(groups, key=lambda group: group.rect.left() if horizontal else group.rect.top())
        for index in range(1, len(ordered)):
            end = max(group.rect.right() if horizontal else group.rect.bottom() for group in ordered[:index])
            start = min(group.rect.left() if horizontal else group.rect.top() for group in ordered[index:])
            if end < start:
                return _Split(orientation, (_partition(ordered[:index]), _partition(ordered[index:])))
    # Hidden/programmatically constructed containers may not yet have useful
    # coordinates. Retain their stable registration order until first layout.
    return _Split(qt.Qt.Orientation.Horizontal, tuple(groups))


def _split_group(target, moving, side):
    rect = target.rect
    left = qt.QRect(rect.left(), rect.top(), max(1, rect.width() // 2), rect.height())
    right = qt.QRect(left.right() + 1, rect.top(), max(1, rect.width() - left.width()), rect.height())
    original = replace(target, rect=right if side == 'left' else left)
    new = _TabGroup((moving,), moving, left if side == 'left' else right)
    return _Split(qt.Qt.Orientation.Horizontal, (new, original) if side == 'left' else (original, new))


def _replace_group(node: _Layout, target: _TabGroup, replacement: _Split) -> _Layout:
    if node is target:
        return replacement
    if isinstance(node, _TabGroup):
        return node
    return replace(node, children=tuple(_replace_group(child, target, replacement) for child in node.children))


def _normalize(node: _Layout) -> _Layout:
    """Flatten adjacent splits on the same axis, retaining leaf order."""
    if isinstance(node, _TabGroup):
        return node
    children = (_normalize(child) for child in node.children)
    return replace(node, children=tuple(part for child in children
        for part in (child.children if isinstance(child, _Split) and child.axis == node.axis else (child,))))


def _leaves(node: _Layout) -> list[_TabGroup]:
    if isinstance(node, _TabGroup):
        return [node]
    return [leaf for child in node.children for leaf in _leaves(child)]


def _apply_layout(workspace, tree):
    """Remove groups, build their split skeleton, then restore tab activation."""
    groups = _leaves(tree)
    for group in groups:
        for dock in group.members:
            workspace.removeDockWidget(dock)
    workspace.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, groups[0].members[0])
    groups[0].members[0].show()
    _build_splits(workspace, tree)
    for group in groups:
        first = group.members[0]
        for dock in group.members:
            if dock is not first:
                workspace.tabifyDockWidget(first, dock)
            dock.show()
        group.active.raise_()


def _build_splits(workspace, node: _Layout):
    if isinstance(node, _TabGroup):
        return
    representatives = [_leaves(child)[0].members[0] for child in node.children]
    for first, second in zip(representatives, representatives[1:]):
        workspace.splitDockWidget(first, second, node.axis)
        second.show()
    for child in node.children:
        _build_splits(workspace, child)
    sizes = []
    for child in node.children:
        rectangles = [leaf.rect for leaf in _leaves(child)]
        extent = qt.QRect(rectangles[0])
        for rectangle in rectangles[1:]:
            extent = extent.united(rectangle)
        sizes.append(max(1, extent.width() if node.axis == qt.Qt.Orientation.Horizontal else extent.height()))
    workspace.resizeDocks(representatives, sizes, node.axis)
