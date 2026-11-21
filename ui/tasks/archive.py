"""Optional legacy ZIP progress presentation; extraction stays in the archive core."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from pathlib import Path
from .. import pyside as qt


def extract_zip_with_progress(source, destination, password=None):
    from ...archives.legacy.compatibility import unzip_file
    window = qt.display_progress_bar(f'Extracting {Path(source).name}')
    try:
        return unzip_file(source, destination, password, progress=window.update_progress)
    finally:
        window.dlg.close()
