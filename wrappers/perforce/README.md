# Perforce wrapper

Generic CLI wrapper extracted from BlueHole. Existing P4File, P4FileGroup,
P4Info, P4FileStatus, P4UserWorkspace and message classes retain their structure,
fields and callback methods. The library imports neither bpy nor add-on preferences.

| File | Ownership |
| --- | --- |
| p4_file.py | Single-file state, checkout/add/sync/move and extension callbacks |
| p4_file_group.py | Group operations and shared checks |
| p4_info.py | Login/server/workspace information |
| p4_file_status.py | Existing status enum |
| p4_utils.py | CLI execution, tagged fstat parsing and binary placeholders |
| p4_messages.py | Shared diagnostic messages |
| runtime.py | Lazy application-supplied configuration |

```python
from commonUtils.wrappers.perforce import P4File, PerforceRuntime, configure_runtime
configure_runtime(PerforceRuntime(executable=lambda platform: '/path/to/p4'))
item = P4File(client_file='/workspace/example.txt')
item.update_fields()
```

Defaults resolve p4 through PATH and do not override environment settings.
Applications may provide executable(platform), environment() (P4USER/P4PORT/
P4CLIENT overrides), and binary_template() callbacks. Providers are evaluated
when used so settings changes remain visible. configure_runtime(None) resets
these callbacks. This is a per-imported-library runtime, not per-repository state.

Execution retains the existing output-line contract and 15-second idle timeout;
fstat diagnostics may use nonzero command exits. Failed/empty command outcomes,
timeouts and cancellation do not masquerade as success. Binary placeholders
preserve existing files. Tagged records include the last entry without requiring
a trailing blank output line.

BlueHole keeps BlendP4File and scene-reload/filter callbacks in its own adapter.
Its compatibility modules re-export the exact shared classes and module state.
Tests use fixture outputs and no live server; consumers still configure/install
Perforce for actual operations.

[Other wrappers](../README.md)
