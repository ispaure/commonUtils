"""Public exports; implementations live in declarations."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from .declarations import (resolve_type, ActionContext, FileType, FileTypeOverride, SelectionAction, FileActivation, BrowserExtension, Feature)

__all__ = ['resolve_type', 'ActionContext', 'FileType', 'FileTypeOverride', 'SelectionAction', 'FileActivation', 'BrowserExtension', 'Feature']
