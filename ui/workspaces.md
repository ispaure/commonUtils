# Workspaces and shared presentation

## Reusable docking workspaces

`commonUtils.ui.workspace.Workspace` owns dockable tabs, full-window dragging,
left/right splits, grouped tab headers, transfer between compatible workspaces,
and cooperative closing. It imports no Logistics features. Supply a factory
returning a QWidget, optionally exposing `view_title`, `title_changed`,
`prepare_close()` and an `idle` signal. A view may set `can_retire` to retain its
worker owners while its visible tab disappears immediately.

Set `allow_new_tabs=False` for externally created documents and
`keep_one_tab=True` to protect the final attached browser tab; floating panes can
still close. `dock_group` restricts transfers to compatible hosts. Override
`reveal_for_drop(global_point)` if dragging should reveal an application-specific
hidden destination. Window dragging and drop placement stay generic; feature
selection, dirty-document prompts and retained original window ownership belong
to the application. `document_host.py` supplies optional hosting and original
window lookup for reusable readers that also work standalone.

Hosted reader close buttons and delayed worker callbacks should use
`document_host.close_document(window)`: embedded documents receive their own
close event and retain save/cancel decisions; independent windows close normally.
Views with no document-close veto may opt into `close_in_background = True` to
remove their workspace tab immediately, before cooperative shutdown begins.
Their owners stay alive until `prepare_close()` succeeds after an `idle` signal.


## Passive archive contents

See [Passive archive contents](archive_view/README.md).

## Shared document and navigation contracts

Optional `document_host` routing embeds a reader/editor in its application's host
or opens it standalone. `request_document_close(window)` returns CloseOutcome:
ACCEPTED, VETOED or PENDING. Owners may implement request_close and an idle signal;
they handle unsaved prompts and asynchronous retirement themselves. A host must
retain pending owners and retry after idle rather than inspect private fields.

`outline.OutlineEntry(id, label, target, depth=0)` carries an opaque navigation
target. OutlineList and OutlineTree populate navigation widgets with set_entries;
items_by_id retains stable selection handles. They provide no filesystem actions.

Reader chrome supplies reading_spin and show_reader_popup with caller-selected
ranges, callbacks and alignment. text_commands.wrap_selection provides one undo
step and UTF-16 cursor accounting with explicit selection/format policy.
entry_views provides selection and sorting mechanics without path semantics.

## Shared result presentation

NotificationCenter retains bounded Notice events, deduplicates IDs and tracks
acknowledgement. Toast renders plain text and an optional details action for a
bounded interval. Applications choose native delivery, event IDs, destination
badges and persistence; these widgets never decide whether an operation is safe.

ResultWorker captures callback result/error under noninteractive logging. Owners
consume them after finished and retain workers until retirement. Cancellation
boundaries and error formatting can be supplied by the caller. Operation retains
its compatibility completed signal; use OperationProgress for finish-safe delivery
with progress and cancellation controls.

Workspace tab bars use horizontal dragging to reorder panes. Drag outside the
tab bar to detach and move the whole pane, then drop to tabify or split. The
workspace keeps its dock order synchronized with native tab order so indexed
close actions and document lists refer to the visible tab.


Floating `WorkspaceDock` panes use regular native window flags, including
minimize/maximize controls and no transient parent. The inner tab header still
supports dragging and double-click reattachment. Their cooperative close handler
and `WA_QuitOnClose=False` preserve the document/worker lifecycle.

