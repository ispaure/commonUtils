# Verified downloads

## Provision a pinned executable or installer

Keep trusted release metadata in your project's manifest. This example expects a
JSON object with the `DownloadSpec` fields and an additional relative `path`:

```python
import json
from pathlib import Path
from commonUtils.runtime.streams.downloads import DownloadSpec, provision

# Example field names: name, version, url, sha256, installed_sha256,
# archive_member (optional), executable (optional), path.
entry = json.loads(Path('tool_release.json').read_text(encoding='utf-8'))
relative_path = Path(entry.pop('path'))
spec = DownloadSpec(**entry)
destination = Path('Software') / relative_path
installed = provision(spec, destination)  # Reuses a matching installed file.
```

Use an HTTPS URL and lowercase 64-character SHA-256 digests. `sha256` verifies the
release bytes; `installed_sha256` verifies the final file. For a raw installer the
hashes are identical. For a ZIP release, set `archive_member` to the exact executable
member and compute the installed hash from that member in the verified release.
Only that member is streamed out. `executable=True` applies Unix execute permission.
The project must validate manifest paths before using untrusted metadata.

`provision` is synchronous and has no prompts. Add `progress(done, total)` and
`cancelled()` callbacks for use in a worker. Cancellation and failure clean staging
and retain a previous destination. Network reads can delay cancellation until the
read returns or times out. `DownloadCancelled` is an alias of `OperationCancelled`.

For a Qt application with an existing QApplication, use the shared prompt/dialog:

```python
from commonUtils.ui.tasks.download import ensure_download

path = ensure_download(spec, destination, parent=window)
if path is not None:
    launch_tool(path)  # Your application owns launching and command arguments.
```

`ensure_download` returns a verified Path, or `None` on decline, cancellation or
download-worker failure. Genuine worker failures remain visible even if Cancel was
also requested. Configuration validation and local filesystem errors outside the
download worker can still raise; the application should handle those at its UI
boundary. With
`install=True`, it also asks before returning an already-downloaded installer for
launch; it does not perform system installation. Download versions and destinations
are entirely project policy.
