"""Optional container policies; legacy Workspace constructors keep their behavior."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

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
