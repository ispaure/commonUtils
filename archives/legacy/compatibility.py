"""Compatibility return conventions over canonical archive operations.

New callers should use explicit operation outcomes/exceptions. This adapter keeps
existing unzip booleans and ZIP root-layout options without duplicate ZIP writers.
"""
from pathlib import Path
import sys
from ...runtime.diagnostics import log, Severity


def unzip_file(source_file, destination_dir, pwd=None, show_progress=False, *, progress=None):
    """Extract with validated paths; return False after reporting an operation error."""
    if show_progress:
        from ...ui.tasks.archive import extract_zip_with_progress
        return extract_zip_with_progress(source_file, destination_dir, pwd)
    from ..zip_access import extract_archive
    try:
        extract_archive(source_file, destination_dir, password=pwd, progress=progress)
        return True
    except Exception as error:
        log(Severity.ERROR, 'Extract ZIP File', f'Could not extract "{source_file}": {error}')
        return False


def unrar_file(source_file, destination_dir, unrar_sw_path=None):
    """Optional external RAR extraction; installation and executable choice are caller-owned."""
    import patoolib
    log(Severity.DEBUG, 'Extract RAR File', f'Extracting archive from "{source_file}" to "{destination_dir}"')
    options = {} if sys.platform == 'win32' else {'program': unrar_sw_path}
    patoolib.extract_archive(source_file, outdir=destination_dir, **options)


def zip_file(source, destination, keep_root=True, *, password=None):
    """Write a verified directory ZIP, preserving layout and overwrite compatibility."""
    from ..zip_access import write_directory
    if not isinstance(source, (str, Path)) or not isinstance(destination, (str, Path)):
        raise TypeError('Source and destination must be strings or Paths')
    write_directory(source, destination, password=password, keep_root=keep_root)
