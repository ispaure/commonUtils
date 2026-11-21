"""Archive member identity and portable metadata, without access/protection policy."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from pathlib import PurePosixPath
import unicodedata
import zipfile


def name_key(name):
    return unicodedata.normalize('NFC', PurePosixPath(name).as_posix()).casefold()



def copy_member_info(member, target):
    """ZipInfo types differ between stdlib and pyzipper; copy portable attributes."""
    if isinstance(target, zipfile.ZipFile):
        cls = zipfile.ZipInfo
    else:
        import pyzipper
        cls = pyzipper.zipfile_aes.AESZipInfo if isinstance(target, pyzipper.AESZipFile) else zipfile.ZipInfo
    result = cls(member.filename, member.date_time)
    for name in ('comment', 'create_system', 'external_attr', 'internal_attr', 'compress_type'):
        setattr(result, name, getattr(member, name))
    # AES reports method 99 in stdlib headers; never copy crypto headers/flags.
    if result.compress_type == 99:
        result.compress_type = zipfile.ZIP_DEFLATED
    return result

