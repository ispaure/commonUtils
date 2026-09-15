# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path
from typing import Union
from .debugUtils import *


def delete_symbolic_link(path: Union[str, Path]) -> bool:
    """
    Deletes a symbolic link without deleting the target it points to.

    The path must be a symbolic link. Real files, directories, junctions and other
    filesystem objects are not deleted by this function.
    """
    path = Path(path)

    if not path.is_symlink():
        log(Severity.CRITICAL, 'Delete Symbolic Link', f'Path is not a symbolic link: "{path}"')

    try:
        path.unlink()
    except Exception as e:
        log(Severity.CRITICAL, 'Delete Symbolic Link', f'Could not delete symbolic link "{path}"\n{type(e).__name__}: {e}')

    if path.is_symlink():
        log(Severity.CRITICAL, 'Delete Symbolic Link', f'Symbolic link still exists after deletion attempt: "{path}"')

    return True


def create_symbolic_link(source: Union[str, Path], destination: Union[str, Path]) -> bool:
    """
    Creates a symbolic link at destination pointing to source.

    The source must exist. The destination parent directory is created if required.
    """
    source = Path(source)
    destination = Path(destination)

    if not source.exists():
        log(Severity.CRITICAL, 'Create Symbolic Link', f'Source does not exist: "{source}"')

    source = source.resolve()

    if destination.exists() or destination.is_symlink():
        log(Severity.CRITICAL, 'Create Symbolic Link', f'Destination already exists: "{destination}"')

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(source, target_is_directory=source.is_dir())
    except Exception as e:
        log(Severity.CRITICAL, 'Create Symbolic Link', f'Could not create symbolic link "{destination}" -> "{source}"\n{type(e).__name__}: {e}')

    if not destination.is_symlink():
        log(Severity.CRITICAL, 'Create Symbolic Link', f'Symbolic link does not exist after creation attempt: "{destination}"')

    return True


def update_symbolic_link(source: Union[str, Path], destination: Union[str, Path],
                         allow_destination_deletion: bool = False, make_writable: bool = False) -> bool:
    """
    Creates or updates a symbolic link at destination pointing to source.

    If destination is already the correct symbolic link, nothing is changed.

    If destination is a symbolic link pointing elsewhere, the existing link is deleted
    and recreated.

    If destination contains another filesystem object, the operation is refused unless
    allow_destination_deletion is True. Enabling allow_destination_deletion explicitly
    authorizes deletion of the existing destination, including real files and complete
    directory trees.

    Junctions are removed without deleting the directory they point to.

    make_writable is propagated when deleting real files or directories.
    """
    source = Path(source)
    destination = Path(destination)
    tool_name = 'Symbolic Link (Update)'
    msg = f'Source: "{source}"\nDestination: "{destination}"'

    if not source.exists():
        log(Severity.CRITICAL, tool_name, f'{msg}\nSource does not exist; Aborting!')

    source = source.resolve()

    # Symbolic links are checked before exists() so broken symbolic links are handled correctly
    if destination.is_symlink():
        try:
            destination_target = destination.resolve(strict=False)
        except Exception as e:
            log(Severity.CRITICAL, tool_name, f'{msg}\nCould not resolve existing symbolic link\n{type(e).__name__}: {e}')

        if destination_target == source:
            log(Severity.DEBUG, tool_name, f'{msg}\nSymbolic Link Already Up to Date!')
            return True

        msg += '\nSymbolic Link exists at destination, but does not match expected source. Updating...'
        delete_symbolic_link(destination)
        create_symbolic_link(source, destination)
        log(Severity.DEBUG, tool_name, msg)
        return True

    # If destination does not exist, simply create the symbolic link
    if not destination.exists():
        msg += '\nSymbolic Link doesn\'t exist at location. Creating...'
        create_symbolic_link(source, destination)
        log(Severity.DEBUG, tool_name, msg)
        return True

    # Something other than a symbolic link already exists at destination
    if not allow_destination_deletion:
        log(Severity.CRITICAL, tool_name, f'{msg}\nDestination already exists and "allow_destination_deletion" is not enabled; Aborting!')

    # Junctions must be removed directly so their targets are never deleted
    if destination.is_junction():
        msg += '\nDestination is a junction. Removing junction...'

        try:
            destination.rmdir()
        except Exception as e:
            log(Severity.CRITICAL, tool_name, f'{msg}\nCould not remove junction\n{type(e).__name__}: {e}')

        if destination.exists() or destination.is_junction():
            log(Severity.CRITICAL, tool_name, f'{msg}\nJunction still exists after deletion attempt: "{destination}"')

    elif destination.is_file():
        msg += '\nDestination is a file. Deleting...'

        from .fileUtils import File
        File(destination).delete_file(make_writable=make_writable)

    elif destination.is_dir():
        msg += '\nDestination is a directory. Deleting...'

        from .dirUtils import Directory
        Directory(destination).delete(make_writable=make_writable)

    else:
        log(Severity.CRITICAL, tool_name, f'{msg}\nDestination is an unsupported filesystem object; Aborting!')

    create_symbolic_link(source, destination)
    log(Severity.DEBUG, tool_name, msg)

    return True
