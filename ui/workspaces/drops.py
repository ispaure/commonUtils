"""Shared drop eligibility, placement, preview and commit for drag transports."""
from typing import NamedTuple
from shiboken6 import isValid


class DropTarget(NamedTuple):
    workspace: object
    anchor: object
    placement: str
    preview: object


def eligible(workspace, dock):
    if (not isValid(workspace) or not isValid(dock) or not isValid(dock.workspace)
            or workspace._closing or dock.workspace._closing or not workspace.isVisible()
            or dock not in dock.workspace.docks or workspace.dock_group != dock.workspace.dock_group):
        return False
    if dock.workspace is not workspace and workspace.policy and workspace.policy.max_tabs is not None:
        if len(workspace.docks) >= workspace.policy.max_tabs:
            return False
    return dock.workspace.can_move_tab(dock, destination=workspace)


class DropCoordinator:
    def __init__(self, source):
        self.source = source
        self.restore_destination = None

    def resolve(self, dock, point, candidates, *, global_point=True):
        for workspace in candidates:
            if not eligible(workspace, dock):
                continue
            local = workspace.mapFromGlobal(point) if global_point else point
            if not global_point or workspace.rect().contains(local):
                return DropTarget(workspace, *workspace._drop_location(local, dock))
        return None

    def reveal(self, point):
        inside = self.source.main_workspace.window().frameGeometry().contains(point)
        if not inside and self.restore_destination is not None:
            self.finish(False)
        elif inside and self.restore_destination is None:
            self.restore_destination = self.source.reveal_for_drop(point)

    def finish(self, committed):
        restore, self.restore_destination = self.restore_destination, None
        if restore is not None and not committed:
            restore()

    @staticmethod
    def clear():
        from .workspace import _workspaces
        for workspace in tuple(_workspaces):
            if isValid(workspace):
                workspace._drop_preview.hide()

    def preview(self, target):
        self.clear()
        if target:
            widget = target.workspace._drop_preview
            widget.setGeometry(target.preview)
            widget.show()
            widget.raise_()

    @staticmethod
    def commit(dock, target):
        if target is None or not eligible(target.workspace, dock):
            return False
        accepted = target.workspace.adopt(dock, placement=target.placement, anchor=target.anchor)
        if accepted:
            target.workspace._update_drop_target()
        return accepted
