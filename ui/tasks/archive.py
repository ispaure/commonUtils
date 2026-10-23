"""Optional legacy ZIP progress presentation; extraction stays in the archive core."""
from pathlib import Path
from .. import pyside as qt


def extract_zip_with_progress(source, destination, password=None):
    from ...archives.legacy.compatibility import unzip_file
    window = qt.display_progress_bar(f'Extracting {Path(source).name}')
    try:
        return unzip_file(source, destination, password, progress=window.update_progress)
    finally:
        window.dlg.close()
