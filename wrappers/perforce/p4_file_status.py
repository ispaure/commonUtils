# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - SHARED PERFORCE WRAPPER, EXTRACTED FROM BLUE HOLE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

# System
import enum


# ----------------------------------------------------------------------------------------------------------------------
# CODE

class P4FileStatus(enum.Enum):
    MARKED_FOR_ADD = 'Marked for add'
    NOT_ADDED = 'Not Added'
    MARKED_FOR_DELETE = 'Marked for delete'
    CHECKOUT_BY_ME = 'Checked out by me'
    CHECKOUT_BY_OTHER = 'Checked out by Others'
    LATEST_REVISION = 'Latest Revision'
    NOT_LATEST_REVISION = 'Not Latest Revision'
    INVALID = 'Invalid'
