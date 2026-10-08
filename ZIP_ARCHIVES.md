# ZIP access

`commonUtils.zip_access` owns archive mechanics. It has no application configuration,
password dialogs, session cache or feature dependencies. It reads ordinary ZIP,
legacy ZipCrypto and WinZip AES, and always uses AES-256 for password-protected writes.
Passwords are UTF-8 strings or bytes; `None` means plain output. Empty passwords
are rejected for encrypted writes. ZIP filenames remain public.

```python
from commonUtils.zip_access import open_archive, extract_archive, create_archive

with open_archive('comic.cbz', password=password) as archive:
    data = archive.read('ComicInfo.xml')
extract_archive('comic.cbz', workspace, password=password)
create_archive([folder, other_file], 'separate.zip', password=password)
```

`ZIPFile.open_archive(password=...)`, `ZIPFile.is_encrypted()` and
`ZIPFile.extract(destination, password=...)` expose these basics on the file type.
The compatibility `zipUtils.unzip_file(..., pwd=...)` returns a boolean;
`extract_archive` raises errors. Neither prompts. Plain and encrypted extraction
use the same layout and streaming code. All names are checked before extraction;
traversal, symbolic links and ambiguous/colliding names are rejected, including
case and Unicode-normalization collisions. Directory entries carrying file data
are rejected rather than silently losing their payload. Individual
files are staged before replacement; extraction as a whole is not transactional,
so callers should supply an isolated disposable workspace.

`create_archive` retains each selected folder's root and empty directories,
deduplicates overlapping selections and rejects collisions. It never replaces
sources or existing outputs. A sibling staged ZIP is fully decrypted and verified
against source entry names and SHA-256 hashes, and source identities are checked
again before exclusive publication.

For archive rewrites, use `authenticate(..., all_members=True, for_rewrite=True)`
before work, `copy_member_info` to convert between stdlib and pyzipper ZipInfo
classes, and `archive_manifest` to verify entry names and decrypted hashes before
replacement. Rewrites reject mixed encrypted/plain file entries; directory headers
may be plain. Authentication errors use `ArchivePasswordError` and never include
the supplied password. An authentication failure may also indicate damaged data.

Dependencies: `pyzipper` for encrypted ZIPs; standard `zipfile` for ordinary ZIPs.
WinZip AES requires a compatible external reader. No filename/header encryption
or 7z support is provided here. Applications own configuration lookup, interactive
prompts, cache policy and the lifetime of plaintext temporary extraction files.

The output containment check resolves filesystem aliases. Source mutation and
competing destination creation are covered by regression tests. Encrypted CRC
and decompression failures (including a legacy ZipCrypto header false positive) are reported as
password-or-damage errors; neither CRC nor AES authentication failures publish a
replacement. SHA-256 verification covers decrypted content, not ZIP headers or
container bytes. Directory-only ZIPs carry no encrypted file payload.

## Cooperative creation cancellation

`create_archive(..., progress=report, cancelled=is_cancelled)` reports
`report(done, total, message)` across hashing, creation and verification; directory
assessment is indeterminate. Cancellation raises `operations.OperationCancelled`
and cleans up staged output without deleting sources or replacing destinations.
Checks occur between chunks and before final publication. `stream_signature` and
`archive_manifest` also accept optional cancellation callbacks. Existing callers
that omit callbacks retain their synchronous, non-cancellable behavior; in
particular, a comic rebuild is allowed to finish and verify its current transaction.
