"""Generic Perforce CLI models, preserving BlueHole's existing class contracts."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from .runtime import PerforceRuntime, configure_runtime
from .p4_file_status import P4FileStatus
from .p4_file import P4File
from .p4_file_group import P4FileGroup
from .p4_info import P4Info
from .p4_utils import P4UserWorkspace, create_p4_user_workspace_cls
