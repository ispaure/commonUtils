# Archive convenience functions

Convenience functions for compression and extraction. Import this module through
`commonUtils.archives.legacy`; general archive operations also live in `commonUtils.archives`.

Import from `commonUtils.archives.legacy`. Implementation and public exports live in
[`compatibility.py`](../../../../../archives/legacy/compatibility.py).

Public entry points: `unzip_file`, `unrar_file`, `zip_file`

[Library overview](../../../overview.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `unzip_file` | Validated streaming extraction for plain/AES ZIPs. |
| `unrar_file` | Extracts rar file to desired location. |
| `zip_file` | Create a zip file from the source to the destination. |

`zip_file` propagates I/O errors, including failure to publish a generated ZIP
under a non-`.zip` extension. A failed move preserves the existing destination
and cleans its private staged ZIP. Both plain and encrypted directory ZIPs use the verified core writer; no intermediate ZIP is published beside a non-`.zip` destination.

Optional `show_progress=True` dispatches to `ui.tasks.archive`; this compatibility adapter does not construct widgets. RAR loads patool only when requested. New operations should use the canonical archive APIs directly.
