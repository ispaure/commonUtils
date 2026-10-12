"""Optional container policies; legacy Workspace constructors keep their behavior."""
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspacePolicy:
    allow_last_tab_detach: bool = True
    show_single_tab_in_main: bool = True
    show_single_tab_in_detached: bool = True
    detached_title: str = '{title}'
    max_tabs: int | None = None


def header_visible(policy, count, detached):
    return count > 1 or count == 1 and (
        policy.show_single_tab_in_detached if detached else policy.show_single_tab_in_main)
