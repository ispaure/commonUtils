"""No-replace publication for verified, newly created archive files."""
import os

from ..runtime.platform import OS, get_os


def publish_created_archive(staged, destination):
    try:
        platform = get_os()
    except RuntimeError:
        platform = OS.UNKNOWN
    if platform is OS.ANDROID:
        # Android can deny hard links even within app-private storage.
        from ..persistence.publication import rename_exclusive
        rename_exclusive(staged, destination)
    else:
        os.link(staged, destination)
