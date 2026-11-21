"""Entry-view mechanics independent of physical paths or archive member identities."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from . import pyside as qt
from ..filesystem.traversal import natural_path_key


def configure_entry_selection(view):
    view.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
    view.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)


def value_less(left, right, *, descending=False, missing_last=True, missing_value=0):
    """Three-way sort decision: None means tie; direction only affects missing values.

    Qt reverses ordinary comparisons for descending sorting. Unknown values stay
    last in either direction when requested; callers own folder grouping.
    """
    if missing_last:
        if (left is None) != (right is None):
            return (left is None) if descending else (left is not None)
    else:
        left = missing_value if left is None else left
        right = missing_value if right is None else right
    return None if left == right else left < right


def label_less(left, right, *, natural=True):
    key = natural_path_key if natural else str.casefold
    return key(left) < key(right)
