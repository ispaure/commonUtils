"""Verified, atomic provisioning of a file or one member of a ZIP release.

Projects supply release metadata and destinations; this module has no UI or
platform policy. Existing files are reused only when their pinned hash matches.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import zipfile

from ..operations import OperationCancelled as DownloadCancelled, check_cancelled
from ..streams import copy_stream, file_sha256, iter_chunks


@dataclass(frozen=True)
class DownloadSpec:
    name: str
    version: str
    url: str
    sha256: str
    installed_sha256: str
    archive_member: str | None = None
    executable: bool = False

    def __post_init__(self):
        if urlparse(self.url).scheme != 'https':
            raise ValueError('Software downloads require HTTPS')
        for value in (self.sha256, self.installed_sha256):
            if not re.fullmatch(r'[0-9a-f]{64}', value):
                raise ValueError('Expected a SHA-256 digest')


def is_ready(spec, destination):
    try:
        return file_sha256(destination) == spec.installed_sha256
    except OSError:
        return False


def provision(spec, destination, *, progress=lambda done, total: None, cancelled=lambda: False):
    """Verify the download and installed payload before atomic replacement.

    Cancellation or any error preserves the previous destination. ZIP members
    are streamed individually, without extracting arbitrary archive paths.
    """
    check_cancelled(cancelled)
    destination = Path(destination)
    if is_ready(spec, destination):
        if spec.executable and os.name != 'nt':
            destination.chmod(destination.stat().st_mode | 0o111)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.download-', dir=destination.parent) as workspace:
        archive_path = Path(workspace) / 'download'
        digest = hashlib.sha256()
        request = Request(spec.url, headers={'User-Agent': 'commonUtils (verified software download)'})
        with urlopen(request, timeout=30) as response, archive_path.open('wb') as output:
            if urlparse(response.geturl()).scheme != 'https':
                raise ValueError('Software download redirected away from HTTPS')
            total = int(response.headers.get('Content-Length', '0'))
            done = 0
            for chunk in iter_chunks(response, cancelled=cancelled):
                output.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                progress(done, total)
        if digest.hexdigest() != spec.sha256:
            raise ValueError(f'{spec.name} download failed SHA-256 verification')
        payload = Path(workspace) / 'payload'
        if spec.archive_member:
            with zipfile.ZipFile(archive_path) as archive:
                matches = [info for info in archive.infolist() if info.filename == spec.archive_member]
                if len(matches) != 1 or matches[0].is_dir():
                    raise ValueError('Release ZIP does not contain one expected executable')
                with archive.open(matches[0]) as source, payload.open('wb') as output:
                    copy_stream(source, output, cancelled=cancelled)
        else:
            archive_path.rename(payload)
        if file_sha256(payload, cancelled=cancelled) != spec.installed_sha256:
            raise ValueError(f'{spec.name} executable/installer failed SHA-256 verification')
        check_cancelled(cancelled)
        if spec.executable and os.name != 'nt':
            payload.chmod(0o755)
        os.replace(payload, destination)
    return destination
