# Qt resource windows

These optional Qt adapters present the toolkit-independent
[resource runtime](../../runtime/resources/resources.md). Import implementations
from their owners; the package alone does not construct widgets or load Qt.
Former `ui.resource_browser`, `ui.resource_picker` and `ui.resource_editor`
modules have been removed.

| Module | Responsibility |
| --- | --- |
| `ui.resources.browser` | `ResourceBrowser` entry presentation, details and resource action jobs |
| `ui.resources.picker` | `ResourcePicker`, `ResourceTaskDialog` and `resource_tasks_pending` shutdown participation |
| `ui.resources.editor` | `ResourceTextWindow` and revision-checked text editing |
| `ui.resources.lifecycle` | `ResourceOperations` worker retention and captured provider identity |

## Changing provider and closing

`ResourceOperations.bind(provider)` captures provider object identity and a new
generation; it refuses a switch while an owned operation is busy. Capture that
identity before starting work, and use `accepts(identity)` before publishing into
the current UI. Retain every worker or child window with `own`; `retire` refuses
to discard a busy owner. Native dialog responses and late worker completions must
not retarget an operation to a newly selected provider.

`stop()` marks the owner closing, requests cancellation from all retained jobs,
and returns **true while busy**. Keep the widget and provider lease until idle;
`resume()` is allowed only after work retires. A resource text editor can veto
closing for unsaved edits before cancellation begins. Task dialogs participate
in the same retirement boundary. Removing a widget is not cancellation.

Selection leases and save/reopen failure semantics are documented in the
[provider guide](../resource-providers.md#shared-open--save-as-selection).
Use the existing resource operation/lifecycle tests and consumer picker/editor
checks when changing these contracts; native dialog checks require a real Qt host.

[Shared UI guide](../ui.md)

## Provider search presentation

`ResourceBrowser(..., path_label=None)` uses Name, Type, Size and Path columns for
recursive results. The optional callback formats a logical provider-relative path;
it must be inexpensive and must not read document bodies. The default joins the
provider root and relative path. Path cells use the placeholder-text palette role;
Name shows only the basename. `ProviderEntryModel.set_search_mode()` also supplies
this projection for hosts that filter already-listed remote entries. Clearing
recursive search restores the normal Name/Date Modified/Size columns and snapshot.
Native provider search likewise shows basenames while retaining full activation
identities in row payloads.
