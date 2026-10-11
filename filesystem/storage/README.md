# Cache and temporary folders

Use `cache_directory()` for data you keep between runs. Use
`temporary_workspace()` for disposable work that should be removed automatically.
These helpers choose a platform-standard commonUtils location.

```python
from pathlib import Path
from commonUtils.filesystem.storage import cache_directory, temporary_workspace

cache = cache_directory()
with temporary_workspace(prefix='my-export-') as directory:
    staged = Path(directory) / 'result.txt'
    staged.write_text('Temporary work', encoding='utf-8')
# The private temporary folder has been removed; the cache remains.
```

Pass `create=False` to `cache_directory()` or `temporary_directory()` when merely
resolving a location. For atomic replacement, stage beside the destination instead
of in temporary storage on another filesystem. See [persistence](../../persistence/README.md).
